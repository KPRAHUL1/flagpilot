import { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  CheckCircle2,
  ExternalLink,
  FlaskConical,
  GitPullRequest,
  KeyRound,
  Play,
  ShieldAlert,
  Sparkles,
  Trash2,
  XCircle,
} from 'lucide-react';
import { api } from './api';
import type { ExperimentRun, HealthResponse } from './types';

const PRESET_PROMPTS = [
  'Test a 1-click express checkout CTA vs standard 2-field form in CheckoutCard.tsx to increase checkout_completed',
  'Test urgency social proof messaging on the CloudPulse Pro upgrade card to lift checkout_completed',
];

function DiffViewer({ diff }: { diff: string }) {
  return (
    <pre className="diff-box">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+') && !line.startsWith('+++')
          ? 'diff-add'
          : line.startsWith('-') && !line.startsWith('---')
            ? 'diff-del'
            : line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')
              ? 'diff-hdr'
              : '';
        return (
          <div key={i} className={cls}>
            {line || ' '}
          </div>
        );
      })}
    </pre>
  );
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState(PRESET_PROMPTS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sessions, setSessions] = useState(80);
  const [showConfig, setShowConfig] = useState(false);
  const [demoSource, setDemoSource] = useState('');

  const [cfgForm, setCfgForm] = useState({
    gemini_api_key: '',
    flagsmith_org_api_key: '',
    flagsmith_environment_key: '',
    github_repo: '',
  });

  const activeRun = runs.find((r) => r.id === selectedId) || runs[0] || null;

  const refreshAll = async () => {
    try {
      const [h, list, src] = await Promise.all([api.health(), api.listRuns(), api.demoSource()]);
      setHealth(h);
      setRuns(list);
      setDemoSource(src.content);
      if (list.length > 0 && !selectedId) {
        setSelectedId(list[0].id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to connect to FlagPilot backend');
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  const handleAction = async (fn: () => Promise<ExperimentRun>) => {
    setBusy(true);
    setError('');
    try {
      const updated = await fn();
      setRuns((prev) => [updated, ...prev.filter((r) => r.id !== updated.id)]);
      setSelectedId(updated.id);
      const src = await api.demoSource();
      setDemoSource(src.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveConfig = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await api.updateConfig(cfgForm);
      setHealth(res.health);
      setShowConfig(false);
      setCfgForm({ gemini_api_key: '', flagsmith_org_api_key: '', flagsmith_environment_key: '', github_repo: '' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save keys');
    } finally {
      setBusy(false);
    }
  };

  const stageStepIndex = (run: ExperimentRun | null) => {
    if (!run) return 0;
    if (run.stage === 'awaiting_setup_approval') return 1;
    if (run.stage === 'running_experiment') return 2;
    if (run.stage === 'awaiting_rollout_approval') return 3;
    if (run.stage === 'shipped_and_cleaned') return 4;
    return 1;
  };

  const currentStep = stageStepIndex(activeRun);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-badge">FP</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>FlagPilot</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>
              Closed-Loop AI Experimentation Engineer • Human-Gated Flagsmith Agent
            </div>
          </div>
        </div>

        <div className="status-pills">
          <span className={`pill ${health?.gemini.configured ? 'ok' : 'warn'}`}>
            <Sparkles size={13} />
            Gemini {health?.gemini.configured ? `(${health.gemini.model})` : 'Fallback Mode'}
          </span>
          <span className={`pill ${health?.flagsmith_api.connected ? 'ok' : 'warn'}`}>
            <FlaskConical size={13} />
            Flagsmith API {health?.flagsmith_api.connected ? 'Live' : 'Sandbox'}
          </span>
          <span className={`pill ${health?.flagsmith_mcp.connected ? 'ok' : 'warn'}`}>
            <Bot size={13} />
            MCP {health?.flagsmith_mcp.connected ? `${health.flagsmith_mcp.tool_count} tools` : 'Idle'}
          </span>
          <span className={`pill ${health?.github_cli.authenticated ? 'ok' : 'warn'}`}>
            <GitPullRequest size={13} />
            gh {health?.github_cli.authenticated ? `@${health.github_cli.account}` : 'Not Logged In'}
          </span>
          <button className="btn btn-ghost" onClick={() => setShowConfig(true)}>
            <KeyRound size={14} /> Configure Keys
          </button>
        </div>
      </header>

      {error && (
        <div style={{ margin: '12px 24px 0', padding: '10px 14px', borderRadius: 10, background: 'rgba(244,63,94,0.14)', border: '1px solid rgba(244,63,94,0.4)', color: '#fda4af', fontSize: 13 }}>
          {error}
        </div>
      )}

      <div className="main-grid">
        {/* Left Sidebar */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <h3 className="card-title">
              <Sparkles size={16} color="#38bdf8" /> Launch Experiment
            </h3>
            <textarea
              className="textarea"
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the feature experiment and success metric..."
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
              {PRESET_PROMPTS.map((p, idx) => (
                <button
                  key={idx}
                  className="btn btn-ghost"
                  style={{ justifyContent: 'flex-start', textAlign: 'left', fontSize: 11, padding: '6px 9px' }}
                  onClick={() => setPrompt(p)}
                >
                  Preset #{idx + 1}: {p.slice(0, 48)}...
                </button>
              ))}
            </div>
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 12 }}
              disabled={busy || prompt.trim().length < 5}
              onClick={() => handleAction(() => api.createRun(prompt))}
            >
              <Bot size={15} /> {busy ? 'Agent Thinking...' : 'Design Flag & Diff'}
            </button>
          </div>

          <div className="card">
            <h3 className="card-title">
              <Activity size={16} color="#10b981" /> Experiment Runs ({runs.length})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {runs.length === 0 && (
                <div style={{ fontSize: 12, color: '#94a3b8' }}>
                  No runs yet. Submit a goal above to inspect `CheckoutCard.tsx` and generate your first Flagsmith experiment!
                </div>
              )}
              {runs.map((r) => (
                <button
                  key={r.id}
                  className="btn btn-ghost"
                  style={{
                    justifyContent: 'space-between',
                    borderColor: activeRun?.id === r.id ? '#38bdf8' : undefined,
                    background: activeRun?.id === r.id ? 'rgba(56,189,248,0.1)' : undefined,
                  }}
                  onClick={() => setSelectedId(r.id)}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 165 }}>
                    {r.plan.flag_name}
                  </span>
                  <span style={{ fontSize: 10, color: '#94a3b8' }}>{r.stage.replace(/_/g, ' ')}</span>
                </button>
              ))}
            </div>
          </div>

          {activeRun && (
            <div className="card">
              <h3 className="card-title">Audit Trail & MCP Logs</h3>
              <div className="audit-list">
                {[...activeRun.audit_log].reverse().map((entry, idx) => (
                  <div key={idx} className="audit-item">
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8', fontWeight: 700, marginBottom: 3 }}>
                      <span>{entry.actor}</span>
                      <span style={{ color: '#64748b', fontWeight: 400 }}>
                        {new Date(entry.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div style={{ fontWeight: 600 }}>{entry.action}</div>
                    <div style={{ color: '#94a3b8', marginTop: 2 }}>{entry.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* Main Workspace */}
        <main style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="stepper">
            {[
              '1. Human Gate #1 (Plan & Diff)',
              '2. Live Traffic & Events',
              '3. Human Gate #2 (Bayesian Verdict)',
              '4. 100% Rollout & Cleanup PR',
            ].map((label, i) => {
              const stepNum = i + 1;
              const cls =
                currentStep > stepNum || (activeRun?.stage === 'shipped_and_cleaned' && stepNum === 4)
                  ? 'done'
                  : currentStep === stepNum
                    ? 'active'
                    : '';
              return (
                <div key={label} className={`step-item ${cls}`}>
                  {label}
                </div>
              );
            })}
          </div>

          {!activeRun ? (
            <div className="card" style={{ padding: 36, textAlign: 'center' }}>
              <FlaskConical size={36} color="#38bdf8" style={{ marginBottom: 10 }} />
              <h2 style={{ margin: '0 0 8px' }}>Ready to Automate Your First Flagsmith Experiment</h2>
              <p style={{ color: '#94a3b8', maxWidth: 560, margin: '0 auto 18px', fontSize: 14, lineHeight: 1.6 }}>
                FlagPilot inspects your target app (<code>demo-app/src/components/CheckoutCard.tsx</code>),
                proposes a multivariate Flagsmith flag & metric, waits for your approval, monitors Bayesian win probability,
                and opens a real GitHub PR removing dead flag code once a winner ships.
              </p>
              <button
                className="btn btn-primary"
                disabled={busy}
                onClick={() => handleAction(() => api.createRun(prompt))}
              >
                <Sparkles size={15} /> Start Demo Experiment Run
              </button>
            </div>
          ) : (
            <>
              {/* Overview Header */}
              <div className="card">
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 12, color: '#38bdf8', fontWeight: 700 }}>
                      RUN #{activeRun.id} • {activeRun.flagsmith_mode.toUpperCase()} • AI: {activeRun.ai_source}
                    </div>
                    <h2 style={{ margin: '4px 0 6px', fontSize: 20 }}>{activeRun.plan.title}</h2>
                    <p style={{ margin: 0, color: '#94a3b8', fontSize: 13 }}>{activeRun.plan.hypothesis}</p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <a
                      href="http://localhost:5174"
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-ghost"
                      style={{ textDecoration: 'none' }}
                    >
                      Open Target Demo App <ExternalLink size={14} />
                    </a>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10, marginTop: 14 }}>
                  <div style={{ background: '#090e1a', padding: 10, borderRadius: 8, border: '1px solid #1e293b' }}>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>Flag Key</div>
                    <code style={{ fontSize: 13, color: '#6ee7b7' }}>{activeRun.plan.flag_name}</code>
                  </div>
                  <div style={{ background: '#090e1a', padding: 10, borderRadius: 8, border: '1px solid #1e293b' }}>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>Conversion Event</div>
                    <code style={{ fontSize: 13, color: '#38bdf8' }}>{activeRun.plan.event_name}</code>
                  </div>
                  <div style={{ background: '#090e1a', padding: 10, borderRadius: 8, border: '1px solid #1e293b' }}>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>Target File</div>
                    <code style={{ fontSize: 12 }}>{activeRun.plan.target_file}</code>
                  </div>
                  <div style={{ background: '#090e1a', padding: 10, borderRadius: 8, border: '1px solid #1e293b' }}>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>Traffic Split</div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>
                      {activeRun.plan.variants.map((v) => `${v.name} ${v.percentage_allocation}%`).join(' / ')}
                    </div>
                  </div>
                </div>
              </div>

              {/* Human Gate #1 */}
              {activeRun.stage === 'awaiting_setup_approval' && (
                <div className="card">
                  <div className="gate-banner">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#fcd34d' }}>
                      <ShieldAlert size={18} /> Human Approval Gate #1 — Review Flagsmith Config & Code Patch
                    </div>
                    <p style={{ margin: '6px 0 0', fontSize: 13, color: '#fde68a' }}>
                      {activeRun.plan.risk_summary}
                    </p>
                  </div>

                  <div style={{ marginBottom: 12, fontSize: 13, fontWeight: 600 }}>
                    Proposed Code Diff (<code>{activeRun.plan.target_file}</code>)
                  </div>
                  <DiffViewer diff={activeRun.plan.unified_diff} />

                  <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                    <button
                      className="btn btn-emerald"
                      disabled={busy}
                      onClick={() => handleAction(() => api.approveSetup(activeRun.id))}
                    >
                      <CheckCircle2 size={16} /> Approve: Provision Flagsmith & Apply Patch
                    </button>
                    <button
                      className="btn btn-danger"
                      disabled={busy}
                      onClick={() => handleAction(() => api.rejectRun(activeRun.id, 'Rejected at Gate #1'))}
                    >
                      <XCircle size={16} /> Reject
                    </button>
                  </div>
                </div>
              )}

              {/* Stage 2 & 3: Live Traffic + Bayesian Verdict */}
              {(activeRun.stage === 'running_experiment' ||
                activeRun.stage === 'awaiting_rollout_approval' ||
                activeRun.stage === 'shipped_and_cleaned') && (
                <div className="card">
                  <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                    <div>
                      <h3 className="card-title" style={{ margin: 0 }}>
                        <FlaskConical size={16} color="#38bdf8" /> Bayesian Experimentation Telemetry
                      </h3>
                      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
                        Exposures: <strong>{activeRun.telemetry.total_exposures}</strong> • Conversions:{' '}
                        <strong>{activeRun.telemetry.total_conversions}</strong> • Source:{' '}
                        <code>{activeRun.telemetry.source}</code>
                      </div>
                    </div>

                    {activeRun.stage !== 'shipped_and_cleaned' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <label style={{ fontSize: 12, color: '#94a3b8' }}>
                          Sessions:
                          <input
                            type="number"
                            min={10}
                            max={500}
                            value={sessions}
                            onChange={(e) => setSessions(Number(e.target.value) || 60)}
                            className="input"
                            style={{ width: 76, marginLeft: 6, padding: '5px 8px', display: 'inline-block' }}
                          />
                        </label>
                        <button
                          className="btn btn-primary"
                          disabled={busy}
                          onClick={() => handleAction(() => api.simulateTraffic(activeRun.id, sessions, 0.42))}
                        >
                          <Play size={14} /> {busy ? 'Streaming...' : 'Simulate Persona Traffic'}
                        </button>
                      </div>
                    )}
                  </div>

                  {activeRun.telemetry.variants.length > 0 ? (
                    <div className="variant-grid">
                      {activeRun.telemetry.variants.map((v) => {
                        const winPct = Math.round(v.win_probability * 1000) / 10;
                        const convPct = Math.round(v.conversion_rate * 1000) / 10;
                        const liftPct = Math.round(v.lift_vs_control * 1000) / 10;
                        const isWinner = activeRun.telemetry.recommended_winner === v.variant_name;
                        return (
                          <div
                            key={v.variant_name}
                            style={{
                              background: '#090e1a',
                              border: `1px solid ${isWinner ? '#10b981' : '#1e293b'}`,
                              borderRadius: 12,
                              padding: 14,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <strong>
                                {v.variant_name} <code>({v.variant_value})</code>
                              </strong>
                              {isWinner && (
                                <span className="pill ok" style={{ fontSize: 11 }}>
                                  Leader
                                </span>
                              )}
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 13 }}>
                              <span>Conv Rate: <strong>{convPct}%</strong></span>
                              <span>{v.conversions}/{v.exposures}</span>
                            </div>
                            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
                              {v.is_control
                                ? 'Control baseline'
                                : `Lift: ${liftPct >= 0 ? '+' : ''}${liftPct}% (95% CI: ${Math.round(v.credible_interval_low * 100)}% to ${Math.round(v.credible_interval_high * 100)}%)`}
                            </div>
                            <div style={{ marginTop: 10, fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
                              <span>Bayesian Win Probability</span>
                              <strong>{winPct}%</strong>
                            </div>
                            <div className="progress-track">
                              <div className="progress-fill" style={{ width: `${Math.min(100, winPct)}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ padding: 16, borderRadius: 10, background: '#090e1a', fontSize: 13, color: '#94a3b8' }}>
                      Flagsmith experiment provisioned! Click <strong>Simulate Persona Traffic</strong> above or interact with the live Demo App to send exposure & conversion events.
                    </div>
                  )}

                  {activeRun.telemetry.verdict_brief && (
                    <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.3)', fontSize: 13 }}>
                      <strong style={{ color: '#38bdf8' }}>Gemini Decision Brief:</strong> {activeRun.telemetry.verdict_brief}
                    </div>
                  )}

                  {activeRun.stage === 'awaiting_rollout_approval' && (
                    <div className="gate-banner" style={{ marginTop: 14, marginBottom: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#fcd34d' }}>
                        <ShieldAlert size={18} /> Human Approval Gate #2 — Ship Winner & Remove Dead Flag Code
                      </div>
                      <p style={{ margin: '6px 0 12px', fontSize: 13, color: '#fde68a' }}>
                        Approving will promote <strong>{activeRun.telemetry.recommended_winner}</strong> to 100% in Flagsmith and open a cleanup PR deleting the losing variant & flag wrapper.
                      </p>
                      <button
                        className="btn btn-emerald"
                        disabled={busy}
                        onClick={() =>
                          handleAction(() =>
                            api.approveRollout(activeRun.id, activeRun.telemetry.recommended_winner || undefined)
                          )
                        }
                      >
                        <Trash2 size={15} /> Approve 100% Rollout & Open Cleanup PR
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Stage 4: Shipped & Cleaned */}
              {activeRun.stage === 'shipped_and_cleaned' && activeRun.cleanup && (
                <div className="card">
                  <h3 className="card-title" style={{ color: '#6ee7b7' }}>
                    <CheckCircle2 size={18} /> Experiment Shipped & Zero Flag Debt Achieved
                  </h3>
                  <p style={{ margin: '0 0 12px', fontSize: 13, color: '#cbd5e1' }}>
                    {activeRun.cleanup.message}
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
                    <span className="pill ok">Winner: {activeRun.cleanup.winning_variant}</span>
                    <span className="pill">Branch: {activeRun.cleanup.branch_name}</span>
                    {activeRun.cleanup.pr_url && (
                      <a
                        href={activeRun.cleanup.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-primary"
                        style={{ textDecoration: 'none', padding: '5px 12px' }}
                      >
                        View GitHub PR <ExternalLink size={14} />
                      </a>
                    )}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                    Zero-Debt Cleanup Diff (<code>{activeRun.cleanup.target_file}</code>)
                  </div>
                  <DiffViewer diff={activeRun.cleanup.cleanup_diff} />
                </div>
              )}

              {/* Current Target File Preview */}
              <div className="card">
                <h3 className="card-title">Live Target File Snapshot (<code>{activeRun.plan.target_file}</code>)</h3>
                <pre className="diff-box" style={{ maxHeight: 220, color: '#cbd5e1' }}>
                  {demoSource}
                </pre>
              </div>
            </>
          )}
        </main>
      </div>

      {/* Config Modal */}
      {showConfig && (
        <div className="modal-backdrop">
          <div className="card" style={{ maxWidth: 480, width: '100%' }}>
            <h3 className="card-title">
              <KeyRound size={16} color="#38bdf8" /> Configure FlagPilot API Keys (.env)
            </h3>
            <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 0 }}>
              Saved directly into your local <code>.env</code> file. Leave a field blank to keep its existing value.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input
                type="password"
                className="input"
                placeholder="GEMINI_API_KEY (AIza...)"
                value={cfgForm.gemini_api_key}
                onChange={(e) => setCfgForm({ ...cfgForm, gemini_api_key: e.target.value })}
              />
              <input
                type="password"
                className="input"
                placeholder="FLAGSMITH_ORG_API_KEY (ser....)"
                value={cfgForm.flagsmith_org_api_key}
                onChange={(e) => setCfgForm({ ...cfgForm, flagsmith_org_api_key: e.target.value })}
              />
              <input
                type="text"
                className="input"
                placeholder="FLAGSMITH_ENVIRONMENT_KEY (client SDK key)"
                value={cfgForm.flagsmith_environment_key}
                onChange={(e) => setCfgForm({ ...cfgForm, flagsmith_environment_key: e.target.value })}
              />
              <input
                type="text"
                className="input"
                placeholder="GITHUB_REPO (optional, e.g. KPRAHUL1/flagpilot)"
                value={cfgForm.github_repo}
                onChange={(e) => setCfgForm({ ...cfgForm, github_repo: e.target.value })}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => setShowConfig(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy} onClick={handleSaveConfig}>
                Save to .env
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
