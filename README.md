# FlagPilot — Closed-Loop AI Experimentation Engineer

> Built for **TGGLEWARS: The Flagsmith Experimentation Hackathon** (Track 02: AI Agents & Feature Flags) by **Team Tamil Loft** (`@kprahul`).

**FlagPilot** turns a plain-English product hypothesis into a live **Flagsmith Experimentation** rollout—and automatically cleans up dead flag code via a real GitHub Pull Request once Bayesian confidence is reached—with **mandatory Human-in-the-Loop approval gates** at every state-changing step.

---

## How FlagPilot Uses Flagsmith

1. **Flagsmith MCP Server (`https://mcp.flagsmith.com`):** Connected via the Python `mcp` Streamable HTTP client to discover and inspect experiments (`list_experiments`), metrics, and tools in real time.
2. **Flagsmith Management REST API:** Provisions multivariate feature flags (`MULTIVARIATE`), creates `experiment-metrics`, creates & starts experiments, and promotes the winning variant to 100%.
3. **Flagsmith SDKs (`@flagsmith/flagsmith` v12.4+ & `flagsmith` Python v6.3+):** Evaluates multivariate flags per identified user and dispatches conversion events (`trackEvent` / `track_event`) feeding Flagsmith's Bayesian stats engine.

---

## 4-Stage Human-Gated Workflow

1. **Prompt $\rightarrow$ Code & Experiment Plan (*Human Gate #1*):** Google Gemini inspects the target component (`demo-app/src/components/CheckoutCard.tsx`), proposes a multivariate flag + conversion metric + unified diff, and pauses for human approval.
2. **Live Sandbox & Persona Traffic Simulator:** Once approved, FlagPilot provisions Flagsmith, applies the patch, and lets you test live in `demo-app` or stream segmented persona sessions.
3. **Bayesian Verdict Brief (*Human Gate #2*):** FlagPilot monitors win probability and lift, drafts a Gemini Decision Brief when confidence hits 95%, and pauses for human rollout sign-off.
4. **100% Rollout + Zero-Debt Cleanup PR:** Upon approval, FlagPilot promotes the winner in Flagsmith and uses `git` + `gh` CLI to open a real GitHub PR removing the losing branch and stale flag wrapper.

---

## Quick Start

### 1. Configure `.env`
Copy `.env.example` to `.env` and fill in your keys (or click **Configure Keys** in the Mission Control UI):

```powershell
Copy-Item .env.example .env
```

Required for full live mode:
- `GEMINI_API_KEY` — Google Gemini API key
- `FLAGSMITH_ORG_API_KEY` — Flagsmith Organisation API key (for Management API + MCP Server)
- `FLAGSMITH_ENVIRONMENT_KEY` — Flagsmith Environment SDK key (for `demo-app` & simulator)

### 2. Install & Run Everything
```powershell
.\start.ps1
```

Or run services individually:
- **Backend API (`:8000`):** `.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000`
- **Mission Control UI (`:5173`):** `cd frontend; npm run dev`
- **Target Demo App (`:5174`):** `cd demo-app; npm run dev`
