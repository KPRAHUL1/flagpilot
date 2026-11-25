from __future__ import annotations

import difflib
import json
import re
from typing import Any

from .config import Settings
from .models import ExperimentTelemetry, ProposedExperimentPlan, VariantOption


def compute_unified_diff(filename: str, before: str, after: str) -> str:
    diff_lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff_lines) or "(no file changes)"


def _slugify(text: str, prefix: str = "exp") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    words = [w for w in cleaned.split("_") if w][:4]
    slug = "_".join(words) or prefix
    return slug[:40]


class GeminiExperimentAgent:
    """Uses Google Gemini to design experiments, instrument code, and strip stale flags."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.gemini_api_key.strip())

    def _call_gemini_json(self, prompt: str) -> dict[str, Any]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key.strip())
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        raw = (response.text or "").strip()
        return json.loads(raw)

    def propose_experiment_plan(
        self,
        user_prompt: str,
        target_file: str,
        file_content: str,
    ) -> tuple[ProposedExperimentPlan, str]:
        """Designs a multivariate Flagsmith experiment and instruments target_file."""
        if self.is_configured:
            try:
                system_prompt = f"""You are FlagPilot, an expert Staff Feature-Flag & Experimentation Engineer.
Analyze the user's experiment goal and the target React/TypeScript file below, and return ONLY valid JSON matching this schema:
{{
  "title": "short experiment title",
  "hypothesis": "clear testable product hypothesis",
  "flag_name": "snake_case_flag_name",
  "flag_description": "concise description",
  "metric_name": "Human Metric Name",
  "event_name": "snake_case_event_name",
  "variants": [
    {{"name": "control", "value": "control", "percentage_allocation": 50, "is_control": true}},
    {{"name": "treatment", "value": "treatment", "percentage_allocation": 50, "is_control": false}}
  ],
  "risk_summary": "1-2 sentences explaining blast radius and why human approval is needed",
  "updated_file_content": "THE COMPLETE UPDATED FILE CONTENT with Flagsmith flag evaluation and flagsmith.trackEvent(event_name) wired cleanly"
}}

Rules:
- Keep existing imports, types, and styling intact.
- Use `useFlagsmith()` or `flagsmith.getValue(flagName)` and `flagsmith.trackEvent(eventName)` cleanly when present, or read from `variant` prop/hook already in the file.
- Ensure percentage allocations sum to 100.
- Do not break TypeScript compilation.

User goal:
{user_prompt}

Target file ({target_file}):
```tsx
{file_content}
```
"""
                data = self._call_gemini_json(system_prompt)
                variants = [VariantOption(**v) for v in data["variants"]]
                updated_content = data["updated_file_content"]
                diff = compute_unified_diff(target_file, file_content, updated_content)
                plan = ProposedExperimentPlan(
                    title=data["title"],
                    hypothesis=data["hypothesis"],
                    flag_name=data["flag_name"],
                    flag_description=data["flag_description"],
                    metric_name=data["metric_name"],
                    event_name=data["event_name"],
                    variants=variants,
                    target_file=target_file,
                    risk_summary=data["risk_summary"],
                    unified_diff=diff,
                    updated_file_content=updated_content,
                )
                return plan, "gemini"
            except Exception as exc:  # noqa: BLE001
                fallback_note = f"Gemini fallback triggered ({exc}); generated deterministic AST-safe plan."
                plan = self._fallback_plan(user_prompt, target_file, file_content, fallback_note)
                return plan, "heuristic_fallback"

        plan = self._fallback_plan(
            user_prompt,
            target_file,
            file_content,
            "GEMINI_API_KEY not configured; generated local deterministic plan.",
        )
        return plan, "heuristic_fallback"

    def _fallback_plan(
        self,
        user_prompt: str,
        target_file: str,
        file_content: str,
        note: str,
    ) -> ProposedExperimentPlan:
        flag_name = f"exp_{_slugify(user_prompt, 'checkout_cta')}"
        event_name = "checkout_completed"
        if "signup" in user_prompt.lower():
            event_name = "signup_completed"
        elif "onboarding" in user_prompt.lower():
            event_name = "first_action_completed"

        updated_content = file_content
        marker = "const activeFlagKey ="
        if marker in updated_content:
            updated_content = re.sub(
                r"const activeFlagKey = ['\"][^'\"]+['\"];",
                f"const activeFlagKey = '{flag_name}';",
                updated_content,
            )
            updated_content = re.sub(
                r"const activeEventName = ['\"][^'\"]+['\"];",
                f"const activeEventName = '{event_name}';",
                updated_content,
            )
        else:
            banner = f"// FlagPilot Experiment: {flag_name} -> tracks '{event_name}'\n"
            updated_content = banner + updated_content

        diff = compute_unified_diff(target_file, file_content, updated_content)
        return ProposedExperimentPlan(
            title=f"Experiment: {user_prompt[:52].strip()}",
            hypothesis=(
                f"Serving the streamlined treatment variant for '{flag_name}' will increase "
                f"'{event_name}' conversion rate compared to control."
            ),
            flag_name=flag_name,
            flag_description=f"FlagPilot multivariate test for: {user_prompt[:120]}",
            metric_name=f"{event_name.replace('_', ' ').title()} Rate",
            event_name=event_name,
            variants=[
                VariantOption(name="control", value="control", percentage_allocation=50, is_control=True),
                VariantOption(name="treatment", value="one_click", percentage_allocation=50, is_control=False),
            ],
            target_file=target_file,
            risk_summary=(
                f"{note} Modifies {target_file} to split 50/50 production traffic and emit "
                f"'{event_name}' events. Human review required before activating flag."
            ),
            unified_diff=diff,
            updated_file_content=updated_content,
        )

    def write_verdict_brief(
        self,
        plan: ProposedExperimentPlan,
        telemetry: ExperimentTelemetry,
    ) -> str:
        """Summarizes Bayesian results into a human-readable decision brief."""
        if not telemetry.variants or telemetry.total_exposures == 0:
            return "No exposures recorded yet. Run simulated sessions or live traffic to evaluate Bayesian win probability."

        winner = max(telemetry.variants, key=lambda v: v.win_probability)
        if self.is_configured:
            try:
                stats_json = json.dumps([v.model_dump() for v in telemetry.variants], indent=2)
                prompt = f"""Summarize this Flagsmith Bayesian A/B test in 2 crisp sentences for an engineer approving a production rollout.
Experiment: {plan.title}
Hypothesis: {plan.hypothesis}
Confidence threshold: {telemetry.confidence_threshold * 100:.0f}%
Telemetry:
{stats_json}

Return JSON: {{"brief": "2 concise sentences"}}"""
                data = self._call_gemini_json(prompt)
                if data.get("brief"):
                    return str(data["brief"])
            except Exception:  # noqa: BLE001
                pass

        win_pct = winner.win_probability * 100
        lift_pct = winner.lift_vs_control * 100
        if telemetry.confidence_met:
            return (
                f"'{winner.variant_name}' ({winner.variant_value}) reached {win_pct:.1f}% Bayesian win probability "
                f"with {lift_pct:+.1f}% lift across {telemetry.total_exposures} exposures. "
                f"Confidence threshold (95%) is met—ready for human-approved 100% rollout and flag cleanup PR."
            )
        return (
            f"'{winner.variant_name}' currently leads at {win_pct:.1f}% win probability ({lift_pct:+.1f}% lift) "
            f"across {telemetry.total_exposures} exposures. Collect more traffic or approve early if desired."
        )

    def generate_cleanup_code(
        self,
        plan: ProposedExperimentPlan,
        current_file_content: str,
        winning_variant_name: str,
    ) -> tuple[str, str]:
        """Removes the losing variant and stale flag evaluation, locking in the winner."""
        winning_opt = next((v for v in plan.variants if v.name == winning_variant_name), plan.variants[-1])

        if self.is_configured:
            try:
                prompt = f"""You are FlagPilot's Stale-Flag Cleanup Engineer.
The Flagsmith experiment '{plan.flag_name}' has concluded. The winning variant is '{winning_opt.name}' (value='{winning_opt.value}').
Remove the conditional A/B branch and stale Flagsmith flag lookup for '{plan.flag_name}' so ONLY the winning '{winning_opt.value}' experience remains cleanly in production.
Preserve TypeScript compilation and clean UI formatting.

Return ONLY valid JSON:
{{"cleaned_file_content": "COMPLETE CLEANED FILE CONTENT"}}

Current file ({plan.target_file}):
```tsx
{current_file_content}
```
"""
                data = self._call_gemini_json(prompt)
                cleaned = data["cleaned_file_content"]
                diff = compute_unified_diff(plan.target_file, current_file_content, cleaned)
                return cleaned, diff
            except Exception:  # noqa: BLE001
                pass

        # Deterministic cleanup fallback: pin winning variant as default & remove experiment banner
        cleaned = current_file_content
        cleaned = re.sub(r"// FlagPilot Experiment:.*\n", "", cleaned)
        cleaned = re.sub(
            r"const defaultWinningVariant = ['\"][^'\"]*['\"];",
            f"const defaultWinningVariant = '{winning_opt.value}';",
            cleaned,
        )
        if f"// Promoted winner: {winning_opt.value}" not in cleaned:
            cleaned = f"// Promoted winner: {winning_opt.value} (stale flag '{plan.flag_name}' cleaned up by FlagPilot)\n" + cleaned
        diff = compute_unified_diff(plan.target_file, current_file_content, cleaned)
        return cleaned, diff
