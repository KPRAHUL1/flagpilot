from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from dotenv import set_key
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import ENV_FILE, ROOT_DIR, get_settings, reload_settings
from .flagsmith_client import FlagsmithClient
from .flagsmith_mcp import FlagsmithMCPClient
from .gemini_agent import GeminiExperimentAgent
from .github_pr import GitHubPRManager, check_gh_status
from .models import (
    ApprovalDecisionRequest,
    AuditLogEntry,
    ConfigUpdateRequest,
    CreateRunRequest,
    ExperimentRun,
    SimulateTrafficRequest,
    utc_now_iso,
)
from .store import RunStore


app = FastAPI(title="FlagPilot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = RunStore(Path(__file__).resolve().parents[1] / ".flagpilot_runs.json")

DEFAULT_TARGET_FILES = [
    "src/components/CheckoutCard.tsx",
    "src/App.tsx",
]


def _pick_target_file(requested: str | None) -> tuple[str, str]:
    settings = get_settings()
    repo_dir = settings.resolved_target_repo()
    candidates = [requested] if requested else DEFAULT_TARGET_FILES
    for rel in candidates:
        if not rel:
            continue
        full = (repo_dir / rel).resolve()
        if full.exists() and full.is_file():
            return rel, full.read_text(encoding="utf-8")
    # Fallback to first .tsx/.ts/.py file found inside target repo
    for ext in ("*.tsx", "*.ts", "*.jsx", "*.py"):
        matches = list(repo_dir.rglob(ext))
        if matches:
            chosen = matches[0]
            return str(chosen.relative_to(repo_dir)).replace("\\", "/"), chosen.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail=f"No source files found inside target repo: {repo_dir}")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    agent = GeminiExperimentAgent(settings)
    fs = FlagsmithClient(settings)
    mcp_client = FlagsmithMCPClient(settings)
    gh_info = check_gh_status()

    fs_ctx = await fs.discover_context() if fs.has_management_key else {"connected": False}
    mcp_info = await mcp_client.list_tools() if mcp_client.is_configured else {"connected": False, "tools": []}

    return {
        "status": "ok",
        "gemini": {
            "configured": agent.is_configured,
            "model": settings.gemini_model,
        },
        "flagsmith_api": {
            "configured": fs.has_management_key,
            "connected": bool(fs_ctx.get("connected")),
            "sdk_key_configured": fs.has_sdk_key or bool(fs_ctx.get("active_environment_key")),
            "active_project_id": fs_ctx.get("active_project_id", ""),
            "active_environment_id": fs_ctx.get("active_environment_id", ""),
        },
        "flagsmith_mcp": {
            "url": settings.flagsmith_mcp_url,
            "connected": bool(mcp_info.get("connected")),
            "tool_count": len(mcp_info.get("tools", [])),
            "tools": mcp_info.get("tools", []),
            "reason": mcp_info.get("reason", ""),
        },
        "github_cli": gh_info,
        "target_repo": str(settings.resolved_target_repo()),
    }


@app.post("/api/config")
async def update_config(payload: ConfigUpdateRequest) -> dict[str, Any]:
    """Saves API keys safely to .env without echoing raw secrets back."""
    if not ENV_FILE.exists():
        example = ROOT_DIR / ".env.example"
        ENV_FILE.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")

    mapping = {
        "GEMINI_API_KEY": payload.gemini_api_key,
        "FLAGSMITH_ORG_API_KEY": payload.flagsmith_org_api_key,
        "FLAGSMITH_ENVIRONMENT_KEY": payload.flagsmith_environment_key,
        "FLAGSMITH_PROJECT_ID": payload.flagsmith_project_id,
        "FLAGSMITH_ENVIRONMENT_ID": payload.flagsmith_environment_id,
        "GITHUB_REPO": payload.github_repo,
    }
    updated_keys: list[str] = []
    for env_key, value in mapping.items():
        if value is not None and value.strip() != "":
            set_key(str(ENV_FILE), env_key, value.strip())
            updated_keys.append(env_key)

    if payload.flagsmith_environment_key and payload.flagsmith_environment_key.strip():
        demo_env = ROOT_DIR / "demo-app" / ".env.local"
        set_key(str(demo_env), "VITE_FLAGSMITH_ENVIRONMENT_KEY", payload.flagsmith_environment_key.strip())

    reload_settings()
    return {"saved": updated_keys, "health": await health()}


@app.get("/api/flagsmith/context")
async def flagsmith_context() -> dict[str, Any]:
    settings = get_settings()
    fs = FlagsmithClient(settings)
    mcp_client = FlagsmithMCPClient(settings)
    ctx = await fs.discover_context()
    mcp_experiments: dict[str, Any] = {}
    if mcp_client.is_configured and ctx.get("active_environment_id"):
        mcp_experiments = await mcp_client.call_tool(
            "list_experiments",
            {"environment_id": int(ctx["active_environment_id"])},
        )
    return {"management": ctx, "mcp_experiments": mcp_experiments}


@app.get("/api/demo-app/source")
async def demo_app_source(target_file: str | None = None) -> dict[str, str]:
    rel, content = _pick_target_file(target_file)
    return {"target_file": rel, "content": content}


@app.get("/api/runs")
async def list_runs() -> list[ExperimentRun]:
    return store.list_runs()


@app.post("/api/runs")
async def create_run(payload: CreateRunRequest) -> ExperimentRun:
    settings = get_settings()
    rel_file, file_content = _pick_target_file(payload.target_file)
    agent = GeminiExperimentAgent(settings)
    plan, ai_source = agent.propose_experiment_plan(payload.prompt, rel_file, file_content)

    run = ExperimentRun(
        id=str(uuid.uuid4())[:8],
        prompt=payload.prompt,
        stage="awaiting_setup_approval",
        ai_source=ai_source,  # type: ignore[arg-type]
        flagsmith_mode="live" if settings.flagsmith_org_api_key.strip() else "sandbox",
        plan=plan,
        original_file_content=file_content,
        audit_log=[
            AuditLogEntry(
                actor="human",
                action="Submitted experiment goal",
                detail=payload.prompt,
            ),
            AuditLogEntry(
                actor="gemini_agent",
                action=f"Designed experiment '{plan.flag_name}' ({ai_source})",
                detail=f"Prepared multivariate variants & code diff for {plan.target_file}; paused at Human Gate #1.",
            ),
        ],
    )
    return store.save_run(run)


@app.post("/api/runs/{run_id}/approve-setup")
async def approve_setup(run_id: str, payload: ApprovalDecisionRequest) -> ExperimentRun:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.stage != "awaiting_setup_approval":
        raise HTTPException(status_code=400, detail=f"Run is in stage '{run.stage}'")

    settings = get_settings()
    fs = FlagsmithClient(settings)
    mcp_client = FlagsmithMCPClient(settings)
    pr_mgr = GitHubPRManager(settings)

    # 1. Human approval logged
    run.audit_log.append(
        AuditLogEntry(
            actor="human",
            action="Approved Human Gate #1 (Flagsmith + Code Patch)",
            detail=f"Approved by {payload.approved_by}. {payload.note}".strip(),
        )
    )

    # 2. Provision multivariate flag + metric + experiment in Flagsmith
    provision = await fs.provision_experiment(run.plan)
    run.flagsmith_mode = provision.get("mode", "sandbox")
    run.flagsmith_feature_id = provision.get("feature_id")
    run.flagsmith_metric_id = provision.get("metric_id")
    run.flagsmith_experiment_id = provision.get("experiment_id")
    for line in provision.get("logs", []):
        run.audit_log.append(AuditLogEntry(actor="flagsmith_api", action="Provision", detail=line))

    # 3. Query Flagsmith MCP server to verify live visibility
    if mcp_client.is_configured:
        mcp_res = await mcp_client.list_tools()
        run.audit_log.append(
            AuditLogEntry(
                actor="flagsmith_mcp",
                action="Verified MCP connection",
                detail=f"Connected={mcp_res.get('connected')} ({len(mcp_res.get('tools', []))} tools)",
            )
        )

    # 4. Apply approved diff to target file
    pr_mgr.apply_file_change(run.plan.target_file, run.plan.updated_file_content)
    run.audit_log.append(
        AuditLogEntry(
            actor="github_cli",
            action="Applied flagged code patch",
            detail=f"Updated {run.plan.target_file} with Flagsmith flag '{run.plan.flag_name}' & trackEvent('{run.plan.event_name}').",
        )
    )

    run.stage = "running_experiment"
    run.updated_at = utc_now_iso()
    return store.save_run(run)


@app.post("/api/runs/{run_id}/reject")
async def reject_run(run_id: str, payload: ApprovalDecisionRequest) -> ExperimentRun:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.stage = "rejected"
    run.audit_log.append(
        AuditLogEntry(
            actor="human",
            action="Rejected proposed action",
            detail=f"Rejected by {payload.approved_by}. {payload.note}".strip(),
        )
    )
    run.updated_at = utc_now_iso()
    return store.save_run(run)


@app.post("/api/runs/{run_id}/simulate")
async def simulate_traffic(run_id: str, payload: SimulateTrafficRequest) -> ExperimentRun:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.stage not in ("running_experiment", "awaiting_rollout_approval"):
        raise HTTPException(status_code=400, detail=f"Cannot simulate traffic in stage '{run.stage}'")

    settings = get_settings()
    fs = FlagsmithClient(settings)
    agent = GeminiExperimentAgent(settings)
    mcp_client = FlagsmithMCPClient(settings)

    telemetry, sim_logs = fs.simulate_sdk_sessions(
        plan=run.plan,
        current_telemetry=run.telemetry,
        sessions=payload.sessions,
        treatment_uplift_bias=payload.treatment_uplift_bias,
    )
    telemetry.verdict_brief = agent.write_verdict_brief(run.plan, telemetry)
    run.telemetry = telemetry

    for line in sim_logs:
        run.audit_log.append(AuditLogEntry(actor="flagsmith_api", action="Traffic & Events", detail=line))

    if mcp_client.is_configured and settings.flagsmith_environment_id:
        mcp_check = await mcp_client.call_tool(
            "list_experiments",
            {"environment_id": int(settings.flagsmith_environment_id)},
        )
        run.audit_log.append(
            AuditLogEntry(
                actor="flagsmith_mcp",
                action="MCP list_experiments poll",
                detail=f"ok={mcp_check.get('ok')} {str(mcp_check.get('content', mcp_check.get('error', '')))[:120]}",
            )
        )

    if telemetry.confidence_met or telemetry.total_exposures >= 60:
        run.stage = "awaiting_rollout_approval"
        run.audit_log.append(
            AuditLogEntry(
                actor="gemini_agent",
                action="Paused at Human Gate #2 (Rollout Approval)",
                detail=telemetry.verdict_brief,
            )
        )

    run.updated_at = utc_now_iso()
    return store.save_run(run)


@app.post("/api/runs/{run_id}/approve-rollout")
async def approve_rollout(run_id: str, payload: ApprovalDecisionRequest) -> ExperimentRun:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.stage not in ("running_experiment", "awaiting_rollout_approval"):
        raise HTTPException(status_code=400, detail=f"Cannot roll out from stage '{run.stage}'")

    settings = get_settings()
    fs = FlagsmithClient(settings)
    agent = GeminiExperimentAgent(settings)
    pr_mgr = GitHubPRManager(settings)

    winning_variant = (
        payload.winning_variant
        or run.telemetry.recommended_winner
        or (run.plan.variants[-1].name if run.plan.variants else "treatment")
    )

    run.audit_log.append(
        AuditLogEntry(
            actor="human",
            action=f"Approved Human Gate #2 (Promote '{winning_variant}' + Cleanup PR)",
            detail=f"Approved by {payload.approved_by}. {payload.note}".strip(),
        )
    )

    # 1. Promote winner to 100% in Flagsmith
    promo_logs = await fs.promote_winner(run.plan, winning_variant, run.flagsmith_feature_id)
    for line in promo_logs:
        run.audit_log.append(AuditLogEntry(actor="flagsmith_api", action="100% Rollout", detail=line))

    # 2. Generate zero-debt cleanup code with Gemini
    _, current_code = _pick_target_file(run.plan.target_file)
    cleaned_code, cleanup_diff = agent.generate_cleanup_code(run.plan, current_code, winning_variant)

    # 3. Open GitHub PR (or commit local cleanup branch if no remote yet)
    cleanup_result = pr_mgr.open_cleanup_pr(
        flag_name=run.plan.flag_name,
        winning_variant=winning_variant,
        target_file=run.plan.target_file,
        cleaned_content=cleaned_code,
        cleanup_diff=cleanup_diff,
        verdict_brief=run.telemetry.verdict_brief,
    )
    run.cleanup = cleanup_result
    run.audit_log.append(
        AuditLogEntry(
            actor="github_cli",
            action=f"Cleanup ({cleanup_result.pr_status})",
            detail=cleanup_result.message,
        )
    )

    run.stage = "shipped_and_cleaned"
    run.updated_at = utc_now_iso()
    return store.save_run(run)
