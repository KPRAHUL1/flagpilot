from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


RunStage = Literal[
    "awaiting_setup_approval",
    "running_experiment",
    "awaiting_rollout_approval",
    "shipped_and_cleaned",
    "rejected",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VariantOption(BaseModel):
    name: str
    value: str
    percentage_allocation: int = 50
    is_control: bool = False


class ProposedExperimentPlan(BaseModel):
    title: str
    hypothesis: str
    flag_name: str
    flag_description: str
    metric_name: str
    event_name: str
    aggregation: Literal["occurrence", "count", "sum", "mean"] = "occurrence"
    direction: Literal["up", "down"] = "up"
    variants: list[VariantOption]
    target_file: str
    risk_summary: str
    unified_diff: str
    updated_file_content: str


class VariantMetrics(BaseModel):
    variant_name: str
    variant_value: str
    is_control: bool = False
    exposures: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0
    lift_vs_control: float = 0.0
    win_probability: float = 0.0
    credible_interval_low: float = 0.0
    credible_interval_high: float = 0.0


class ExperimentTelemetry(BaseModel):
    source: Literal["flagsmith_live", "local_sandbox"] = "local_sandbox"
    total_exposures: int = 0
    total_conversions: int = 0
    recommended_winner: str | None = None
    confidence_met: bool = False
    confidence_threshold: float = 0.95
    verdict_brief: str = ""
    variants: list[VariantMetrics] = Field(default_factory=list)
    last_updated_at: str = Field(default_factory=utc_now_iso)


class CleanupPRResult(BaseModel):
    winning_variant: str
    target_file: str
    cleanup_diff: str
    cleaned_file_content: str
    branch_name: str = ""
    pr_url: str = ""
    pr_status: Literal["opened_github_pr", "local_branch_committed", "preview_only"] = "preview_only"
    message: str = ""


class AuditLogEntry(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    actor: Literal["gemini_agent", "flagsmith_mcp", "flagsmith_api", "human", "github_cli", "system"]
    action: str
    detail: str


class ExperimentRun(BaseModel):
    id: str
    prompt: str
    stage: RunStage
    ai_source: Literal["gemini", "heuristic_fallback"] = "gemini"
    flagsmith_mode: Literal["live", "sandbox"] = "sandbox"
    flagsmith_feature_id: int | None = None
    flagsmith_metric_id: int | None = None
    flagsmith_experiment_id: int | None = None
    plan: ProposedExperimentPlan
    original_file_content: str = ""
    telemetry: ExperimentTelemetry = Field(default_factory=ExperimentTelemetry)
    cleanup: CleanupPRResult | None = None
    audit_log: list[AuditLogEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class CreateRunRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=2000)
    target_file: str | None = None


class ApprovalDecisionRequest(BaseModel):
    approved_by: str = "Rahul K (@kprahul)"
    note: str = ""
    winning_variant: str | None = None


class SimulateTrafficRequest(BaseModel):
    sessions: int = Field(default=60, ge=10, le=500)
    treatment_uplift_bias: float = Field(default=0.38, ge=-0.5, le=0.8)


class ConfigUpdateRequest(BaseModel):
    gemini_api_key: str | None = None
    flagsmith_org_api_key: str | None = None
    flagsmith_environment_key: str | None = None
    flagsmith_project_id: str | None = None
    flagsmith_environment_id: str | None = None
    github_repo: str | None = None
