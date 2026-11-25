export type RunStage =
  | 'awaiting_setup_approval'
  | 'running_experiment'
  | 'awaiting_rollout_approval'
  | 'shipped_and_cleaned'
  | 'rejected';

export interface VariantOption {
  name: string;
  value: string;
  percentage_allocation: number;
  is_control: boolean;
}

export interface ProposedExperimentPlan {
  title: string;
  hypothesis: string;
  flag_name: string;
  flag_description: string;
  metric_name: string;
  event_name: string;
  aggregation: 'occurrence' | 'count' | 'sum' | 'mean';
  direction: 'up' | 'down';
  variants: VariantOption[];
  target_file: string;
  risk_summary: string;
  unified_diff: string;
  updated_file_content: string;
}

export interface VariantMetrics {
  variant_name: string;
  variant_value: string;
  is_control: boolean;
  exposures: number;
  conversions: number;
  conversion_rate: number;
  lift_vs_control: number;
  win_probability: number;
  credible_interval_low: number;
  credible_interval_high: number;
}

export interface ExperimentTelemetry {
  source: 'flagsmith_live' | 'local_sandbox';
  total_exposures: number;
  total_conversions: number;
  recommended_winner: string | null;
  confidence_met: boolean;
  confidence_threshold: number;
  verdict_brief: string;
  variants: VariantMetrics[];
  last_updated_at: string;
}

export interface CleanupPRResult {
  winning_variant: string;
  target_file: string;
  cleanup_diff: string;
  cleaned_file_content: string;
  branch_name: string;
  pr_url: string;
  pr_status: 'opened_github_pr' | 'local_branch_committed' | 'preview_only';
  message: string;
}

export interface AuditLogEntry {
  timestamp: string;
  actor: 'gemini_agent' | 'flagsmith_mcp' | 'flagsmith_api' | 'human' | 'github_cli' | 'system';
  action: string;
  detail: string;
}

export interface ExperimentRun {
  id: string;
  prompt: string;
  stage: RunStage;
  ai_source: 'gemini' | 'heuristic_fallback';
  flagsmith_mode: 'live' | 'sandbox';
  flagsmith_feature_id: number | null;
  flagsmith_metric_id: number | null;
  flagsmith_experiment_id: number | null;
  plan: ProposedExperimentPlan;
  original_file_content: string;
  telemetry: ExperimentTelemetry;
  cleanup: CleanupPRResult | null;
  audit_log: AuditLogEntry[];
  created_at: string;
  updated_at: string;
}

export interface HealthResponse {
  status: string;
  gemini: { configured: boolean; model: string };
  flagsmith_api: {
    configured: boolean;
    connected: boolean;
    sdk_key_configured: boolean;
    active_project_id: string;
    active_environment_id: string;
  };
  flagsmith_mcp: {
    url: string;
    connected: boolean;
    tool_count: number;
    tools: { name: string; description: string }[];
    reason?: string;
  };
  github_cli: { installed: boolean; authenticated: boolean; account: string };
  target_repo: string;
}
