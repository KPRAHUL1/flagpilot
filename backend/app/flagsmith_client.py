from __future__ import annotations

import math
import random
from typing import Any
import httpx

from .config import Settings
from .models import (
    ExperimentTelemetry,
    ProposedExperimentPlan,
    VariantMetrics,
    utc_now_iso,
)


def _bayesian_win_probability(
    c_exp: int,
    c_conv: int,
    t_exp: int,
    t_conv: int,
    draws: int = 3000,
) -> tuple[float, float, float]:
    """Monte Carlo Beta-Binomial win probability & 95% credible interval for lift."""
    if c_exp <= 0 or t_exp <= 0:
        return 0.5, 0.0, 0.0
    rng = random.Random(42 + c_exp + c_conv + t_exp + t_conv)
    alpha_c, beta_c = 1 + max(0, c_conv), 1 + max(0, c_exp - c_conv)
    alpha_t, beta_t = 1 + max(0, t_conv), 1 + max(0, t_exp - t_conv)

    wins = 0
    lifts: list[float] = []
    for _ in range(draws):
        p_c = rng.betavariate(alpha_c, beta_c)
        p_t = rng.betavariate(alpha_t, beta_t)
        if p_t > p_c:
            wins += 1
        if p_c > 0:
            lifts.append((p_t - p_c) / p_c)

    lifts.sort()
    ci_low = lifts[int(0.025 * len(lifts))] if lifts else 0.0
    ci_high = lifts[int(0.975 * len(lifts))] if lifts else 0.0
    return wins / draws, ci_low, ci_high


class FlagsmithClient:
    """Interfaces with Flagsmith Management API, Experimentation endpoints, and Python SDK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def has_management_key(self) -> bool:
        return bool(self.settings.flagsmith_org_api_key.strip())

    @property
    def has_sdk_key(self) -> bool:
        return bool(self.settings.flagsmith_environment_key.strip())

    def _mgmt_headers(self) -> dict[str, str]:
        token = self.settings.flagsmith_org_api_key.strip()
        if token.lower().startswith("api-key "):
            auth = token
        else:
            auth = f"Api-Key {token}"
        return {
            "Authorization": auth,
            "Content-Type": "application/json",
        }

    async def discover_context(self) -> dict[str, Any]:
        """Lists organisations, projects, and environments using the management API key."""
        if not self.has_management_key:
            return {"connected": False, "reason": "FLAGSMITH_ORG_API_KEY not configured"}

        base = self.settings.flagsmith_api_url.rstrip("/")
        async with httpx.AsyncClient(timeout=15.0, headers=self._mgmt_headers()) as client:
            orgs_resp = await client.get(f"{base}/organisations/")
            if orgs_resp.status_code >= 400:
                return {"connected": False, "reason": f"Auth/API error {orgs_resp.status_code}: {orgs_resp.text[:200]}"}
            orgs_data = orgs_resp.json()
            orgs = orgs_data.get("results", orgs_data) if isinstance(orgs_data, dict) else orgs_data

            proj_resp = await client.get(f"{base}/projects/")
            projects = []
            if proj_resp.status_code < 400:
                p_data = proj_resp.json()
                projects = p_data.get("results", p_data) if isinstance(p_data, dict) else p_data

            selected_project_id = self.settings.flagsmith_project_id or (str(projects[0]["id"]) if projects else "")
            envs = []
            if selected_project_id:
                env_resp = await client.get(f"{base}/environments/?project={selected_project_id}")
                if env_resp.status_code < 400:
                    e_data = env_resp.json()
                    envs = e_data.get("results", e_data) if isinstance(e_data, dict) else e_data

            selected_env = None
            if envs:
                if self.settings.flagsmith_environment_id:
                    selected_env = next(
                        (e for e in envs if str(e.get("id")) == str(self.settings.flagsmith_environment_id)),
                        envs[0],
                    )
                else:
                    selected_env = envs[0]

            return {
                "connected": True,
                "organisations": [{"id": o.get("id"), "name": o.get("name")} for o in orgs],
                "projects": [{"id": p.get("id"), "name": p.get("name")} for p in projects],
                "environments": [
                    {
                        "id": e.get("id"),
                        "name": e.get("name"),
                        "api_key": e.get("api_key"),
                    }
                    for e in envs
                ],
                "active_project_id": selected_project_id,
                "active_environment_id": str(selected_env.get("id")) if selected_env else "",
                "active_environment_key": self.settings.flagsmith_environment_key or (selected_env.get("api_key", "") if selected_env else ""),
            }

    async def provision_experiment(self, plan: ProposedExperimentPlan) -> dict[str, Any]:
        """Creates multivariate feature flag, experiment metric, and experiment in Flagsmith."""
        if not self.has_management_key:
            return {"mode": "sandbox", "reason": "No FLAGSMITH_ORG_API_KEY configured"}

        ctx = await self.discover_context()
        if not ctx.get("connected") or not ctx.get("active_project_id") or not ctx.get("active_environment_key"):
            return {"mode": "sandbox", "reason": ctx.get("reason", "Could not resolve project/environment")}

        base = self.settings.flagsmith_api_url.rstrip("/")
        project_id = ctx["active_project_id"]
        env_key = ctx["active_environment_key"]
        logs: list[str] = []

        async with httpx.AsyncClient(timeout=20.0, headers=self._mgmt_headers()) as client:
            # 1. Create or reuse multivariate feature flag
            mv_options = [
                {
                    "type": "unicode",
                    "string_value": v.value,
                    "default_percentage_allocation": v.percentage_allocation,
                }
                for v in plan.variants
            ]
            feature_payload = {
                "name": plan.flag_name,
                "description": plan.flag_description,
                "type": "MULTIVARIATE",
                "default_enabled": True,
                "initial_value": plan.variants[0].value if plan.variants else "control",
                "multivariate_options": mv_options,
            }
            feat_resp = await client.post(f"{base}/projects/{project_id}/features/", json=feature_payload)
            feature_id: int | None = None
            if feat_resp.status_code < 400:
                feature_id = feat_resp.json().get("id")
                logs.append(f"Created multivariate feature '{plan.flag_name}' (id={feature_id})")
            else:
                # Try finding existing feature by name
                list_resp = await client.get(f"{base}/projects/{project_id}/features/?search={plan.flag_name}")
                if list_resp.status_code < 400:
                    results = list_resp.json().get("results", [])
                    match = next((f for f in results if f.get("name") == plan.flag_name), None)
                    if match:
                        feature_id = match.get("id")
                        logs.append(f"Reused existing feature '{plan.flag_name}' (id={feature_id})")
                if feature_id is None:
                    logs.append(f"Feature creation returned {feat_resp.status_code}: {feat_resp.text[:160]}")

            # 2. Ensure feature is enabled in the target environment
            if feature_id is not None:
                fs_resp = await client.get(f"{base}/environments/{env_key}/featurestates/?feature={feature_id}")
                if fs_resp.status_code < 400:
                    fs_items = fs_resp.json().get("results", [])
                    if fs_items:
                        fs_id = fs_items[0]["id"]
                        await client.patch(
                            f"{base}/environments/{env_key}/featurestates/{fs_id}/",
                            json={"enabled": True},
                        )
                        logs.append(f"Enabled feature state {fs_id} in environment")

            # 3. Create Experiment Metric
            metric_id: int | None = None
            metric_payload = {
                "name": plan.metric_name,
                "aggregation": plan.aggregation,
                "direction": plan.direction,
                "definition": {
                    "version": 1,
                    "event": plan.event_name,
                },
            }
            met_resp = await client.post(
                f"{base}/environments/{env_key}/experiment-metrics/",
                json=metric_payload,
            )
            if met_resp.status_code < 400:
                metric_id = met_resp.json().get("id")
                logs.append(f"Created experiment metric '{plan.metric_name}' (id={metric_id})")
            else:
                logs.append(f"Metric API status {met_resp.status_code}: {met_resp.text[:140]}")

            # 4. Create & Start Experiment (best-effort depending on warehouse connection)
            experiment_id: int | None = None
            if feature_id is not None and metric_id is not None:
                exp_payload = {
                    "name": plan.title,
                    "description": plan.hypothesis,
                    "feature": feature_id,
                    "primary_metric": metric_id,
                }
                exp_resp = await client.post(
                    f"{base}/environments/{env_key}/experiments/",
                    json=exp_payload,
                )
                if exp_resp.status_code < 400:
                    experiment_id = exp_resp.json().get("id")
                    logs.append(f"Created Flagsmith experiment (id={experiment_id})")
                    start_resp = await client.post(
                        f"{base}/environments/{env_key}/experiments/{experiment_id}/start/",
                        json={},
                    )
                    if start_resp.status_code < 400:
                        logs.append(f"Started Flagsmith experiment (id={experiment_id})")
                else:
                    logs.append(f"Experiment API status {exp_resp.status_code}: {exp_resp.text[:140]}")

        return {
            "mode": "live" if feature_id is not None else "sandbox",
            "environment_key": env_key,
            "feature_id": feature_id,
            "metric_id": metric_id,
            "experiment_id": experiment_id,
            "logs": logs,
        }

    def simulate_sdk_sessions(
        self,
        plan: ProposedExperimentPlan,
        current_telemetry: ExperimentTelemetry,
        sessions: int,
        treatment_uplift_bias: float,
    ) -> tuple[ExperimentTelemetry, list[str]]:
        """
        Evaluates the multivariate flag and sends conversion events via Flagsmith Python SDK
        when environment key is configured, and updates Bayesian telemetry.
        """
        logs: list[str] = []
        sdk_client = None
        if self.has_sdk_key:
            try:
                from flagsmith import Flagsmith

                sdk_client = Flagsmith(environment_key=self.settings.flagsmith_environment_key.strip())
                logs.append("Initialized Flagsmith Python SDK for live identity evaluations & trackEvent")
            except Exception as exc:  # noqa: BLE001
                logs.append(f"SDK init fallback: {exc}")

        personas = ["mobile_dev", "startup_founder", "enterprise_pm", "student_builder", "returning_user"]
        existing = {v.variant_name: v for v in current_telemetry.variants}
        counts: dict[str, list[int]] = {}
        for opt in plan.variants:
            prev = existing.get(opt.name)
            counts[opt.name] = [
                prev.exposures if prev else 0,
                prev.conversions if prev else 0,
            ]

        rng = random.Random()
        base_rate = 0.24
        live_events_sent = 0

        for idx in range(sessions):
            persona = personas[idx % len(personas)]
            identity_id = f"flagpilot_sim_{persona}_{rng.randint(10000, 99999)}"
            assigned_variant = None

            if sdk_client is not None:
                try:
                    flags = sdk_client.get_identity_flags(
                        identifier=identity_id,
                        traits={"persona": persona, "source": "flagpilot_simulator"},
                    )
                    val = str(flags.get_feature_value(plan.flag_name) or "")
                    matched = next((v for v in plan.variants if v.value == val), None)
                    if matched:
                        assigned_variant = matched
                except Exception:  # noqa: BLE001
                    assigned_variant = None

            if assigned_variant is None:
                # Deterministic weighted split if flag not yet seeded in live env
                weights = [max(1, v.percentage_allocation) for v in plan.variants]
                assigned_variant = rng.choices(plan.variants, weights=weights, k=1)[0]

            counts[assigned_variant.name][0] += 1
            prob = base_rate if assigned_variant.is_control else max(0.05, min(0.85, base_rate * (1 + treatment_uplift_bias)))
            converted = rng.random() < prob
            if converted:
                counts[assigned_variant.name][1] += 1
                if sdk_client is not None and hasattr(sdk_client, "track_event"):
                    try:
                        sdk_client.track_event(
                            event_name=plan.event_name,
                            identity=identity_id,
                        )
                        live_events_sent += 1
                    except Exception:  # noqa: BLE001
                        pass

        if sdk_client is not None:
            logs.append(f"Evaluated {sessions} identities via Flagsmith SDK ({live_events_sent} conversion events dispatched)")
        else:
            logs.append(f"Simulated {sessions} persona sessions in local sandbox (add FLAGSMITH_ENVIRONMENT_KEY for live SDK events)")

        control_opt = next((v for v in plan.variants if v.is_control), plan.variants[0])
        c_exp, c_conv = counts[control_opt.name]
        c_rate = (c_conv / c_exp) if c_exp > 0 else 0.0

        variant_metrics: list[VariantMetrics] = []
        best_non_control: VariantMetrics | None = None

        for opt in plan.variants:
            exp, conv = counts[opt.name]
            rate = (conv / exp) if exp > 0 else 0.0
            if opt.name == control_opt.name:
                vm = VariantMetrics(
                    variant_name=opt.name,
                    variant_value=opt.value,
                    is_control=True,
                    exposures=exp,
                    conversions=conv,
                    conversion_rate=round(rate, 4),
                    lift_vs_control=0.0,
                    win_probability=0.0,
                )
            else:
                win_prob, ci_l, ci_h = _bayesian_win_probability(c_exp, c_conv, exp, conv)
                lift = ((rate - c_rate) / c_rate) if c_rate > 0 else 0.0
                vm = VariantMetrics(
                    variant_name=opt.name,
                    variant_value=opt.value,
                    is_control=False,
                    exposures=exp,
                    conversions=conv,
                    conversion_rate=round(rate, 4),
                    lift_vs_control=round(lift, 4),
                    win_probability=round(win_prob, 4),
                    credible_interval_low=round(ci_l, 4),
                    credible_interval_high=round(ci_h, 4),
                )
                if best_non_control is None or vm.win_probability > best_non_control.win_probability:
                    best_non_control = vm
            variant_metrics.append(vm)

        # Backfill control win_probability as 1 - best challenger win_probability
        if best_non_control is not None:
            for vm in variant_metrics:
                if vm.is_control:
                    vm.win_probability = round(max(0.0, 1.0 - best_non_control.win_probability), 4)

        total_exp = sum(v.exposures for v in variant_metrics)
        total_conv = sum(v.conversions for v in variant_metrics)
        confidence_met = bool(best_non_control and best_non_control.win_probability >= 0.95)
        winner = (
            best_non_control.variant_name
            if confidence_met and best_non_control
            else (
                max(variant_metrics, key=lambda v: v.win_probability).variant_name
                if total_exp > 0
                else None
            )
        )

        telemetry = ExperimentTelemetry(
            source="flagsmith_live" if self.has_sdk_key else "local_sandbox",
            total_exposures=total_exp,
            total_conversions=total_conv,
            recommended_winner=winner,
            confidence_met=confidence_met,
            confidence_threshold=0.95,
            variants=variant_metrics,
            last_updated_at=utc_now_iso(),
        )
        return telemetry, logs

    async def promote_winner(
        self,
        plan: ProposedExperimentPlan,
        winning_variant_name: str,
        feature_id: int | None,
    ) -> list[str]:
        """Promotes the winning variant to 100% in Flagsmith via Management API."""
        logs: list[str] = []
        winning_opt = next((v for v in plan.variants if v.name == winning_variant_name), plan.variants[-1])

        if not self.has_management_key or feature_id is None:
            logs.append(
                f"Sandbox rollout: promoted '{winning_opt.name}' ({winning_opt.value}) to 100% allocation"
            )
            return logs

        ctx = await self.discover_context()
        project_id = ctx.get("active_project_id")
        env_key = ctx.get("active_environment_key")
        if not project_id or not env_key:
            logs.append("Could not resolve Flagsmith project/env during winner promotion")
            return logs

        base = self.settings.flagsmith_api_url.rstrip("/")
        async with httpx.AsyncClient(timeout=20.0, headers=self._mgmt_headers()) as client:
            feat_resp = await client.get(f"{base}/projects/{project_id}/features/{feature_id}/")
            if feat_resp.status_code < 400:
                feat_data = feat_resp.json()
                mv_options = feat_data.get("multivariate_options", [])
                updated_mv = []
                for opt in mv_options:
                    is_win = opt.get("string_value") == winning_opt.value
                    updated_mv.append({
                        "id": opt.get("id"),
                        "type": opt.get("type", "unicode"),
                        "string_value": opt.get("string_value"),
                        "default_percentage_allocation": 100 if is_win else 0,
                    })
                patch_resp = await client.patch(
                    f"{base}/projects/{project_id}/features/{feature_id}/",
                    json={
                        "initial_value": winning_opt.value,
                        "multivariate_options": updated_mv,
                    },
                )
                if patch_resp.status_code < 400:
                    logs.append(
                        f"Promoted Flagsmith feature '{plan.flag_name}' (id={feature_id}) to 100% '{winning_opt.value}'"
                    )
                else:
                    logs.append(f"Feature promotion status {patch_resp.status_code}: {patch_resp.text[:150]}")
        return logs
