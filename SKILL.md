---
name: decision-engine
version: "1.2"
description: >
  Hermes Decision Engine — cost-aware task routing + real-time budget monitoring.
  Routes tasks to optimal models (MiniMax → Kimi → Grok) based on complexity,
  budget status, time-of-day, and domain overrides. Auto-routing currently disabled.
version_date: "2026-04-25"
budget_live:
  today_cost: 13.77
  budget_limit: 10.00
  percent_used: 138
  status: MONITORING
  routing_mode: DISABLED
  updated_at: "2026-04-23 21:58"
  top_models_today:
    - kimi-k2.6: 22 req, 24,481,395 tok, $11.72
    - kimi-k2.6: 5 req, 1,122,286 tok, $0.87
    - kimi-k2.6: 191 req, 783,049 tok, $0.53
trigger:
  - "manual check: run 'cat ~/.hermes/data/budget_status.md'"
  - "when user asks about cost or model recommendation"
---

# Decision Engine — ⚠️ MONITORING ONLY (Auto Routing Disabled)

## ⚠️ STATUS: AUTO ROUTING DISABLED (2026-04-23)

All automatic model routing has been **disabled by user decision**.
The system now operates in **data collection + manual mode only**.

**What this means:**
- ✅ Cost data is still collected and displayed
- ✅ `budget_status.md` still updates hourly
- ✅ You can still ask "how much have I spent today?"
- ❌ NO automatic model selection based on budget
- ❌ NO CRITICAL warnings blocking expensive models
- ❌ NO forced MiniMax when budget is high
- ℹ️ **You control all model selection manually**

## Quick Reference

```
User Prompt → ComplexityScorer (0-10) + MetricsAPI ($ today)
                    ↓
         DecisionRouter → (model, delegate?, reasoning)
                    ↓
              Execute with chosen strategy
```

## Session Start Protocol

**Every new session MUST do one of the following BEFORE choosing a model or delegate_task:**

### Option A: Run the enable script (recommended)
```bash
python3 /home/sunnycsl/.hermes/scripts/decision_engine/enable_for_session.py
```
This prints the current budget status and routing rules.

### Option B: Read the status file
```bash
cat /home/sunnycsl/.hermes/data/budget_status.md
```

### Option C: Load this skill
When you load this skill (`skill_view("decision-engine")`), the YAML frontmatter
above contains the **live budget state** (updated hourly by cron).

## Natural Language Triggers (Auto-Detect)

You **do not need to say technical terms**. I will auto-detect budget/routing context from normal conversation.

### 🔔 Ultra-Simple Triggers (Single word/phrase)

| What you say | What I do |
|-------------|-----------|
| "ready" / "go" / "start" | Show current budget status + I'm ready |
| "check" / "status" / "點" | Show budget status + today's usage |
| "budget" / "quota" / "錢" | Show detailed cost breakdown |
| "慳錢" / "平啲" / "free" | Switch to cheapest model (MiniMax) |
| "delegate" / "派" / "拆" | Analyze if task should be split |
| "model" / "用邊個" / "點做" | Show model recommendation for next task |
| "help" / "點搞" / "教路" | Show available commands + current budget |

### 💰 Cost Awareness (Casual speech)

| What you say | What I do |
|-------------|-----------|
| "今日使咗幾多" / "今日用咗幾多" | Show today's spend |
| "仲有幾多" / "仲剩幾多" | Show remaining budget |
| "慳啲" / "唔好咁貴" / "用平啲" | Lock to MiniMax, disable delegate |
| "over budget" / "超支" | Show warning + force cheap mode |
| "貴唔貴" / "值得咩" | Cost estimate before execution |
| "token 幾多" / "貴唔貴" | Estimate token cost |

### 🔄 Model Selection (Natural)

| What you say | What I do |
|-------------|-----------|
| "用咩 model" / "邊個 model 好" | Recommend model based on budget + task |
| "用 grok" / "用 kimi" / "用 MiniMax" | Override model (if budget allows) |
| "換個 model" / "轉 model" | Show alternatives |
| "點解用呢個" / "點解唔用 grok" | Explain routing decision |
| "呢個要用邊個做" | Analyze complexity → recommend model |

### 📈 Task Complexity (Embedded in normal requests)

When you ask me to do work, I **automatically** check complexity + budget:

| Your request | My auto-action |
|-------------|----------------|
| "寫個程式" / "寫個 script" | Score complexity → decide model |
| "分析下..." / "研究下..." | Score complexity → decide model |
| "做個報告" / "整理下..." | Score complexity → decide model |
| "檢查下..." / "睇下..." | Score complexity → decide model |
| "大工程" / "複雜嘢" / "重要嘢" | High complexity → suggest delegation |
| "簡單嘢" / "小嘢" / "快啲搞" | Low complexity → direct execution |

### 🚨 CRITICAL Override (Always enforced)

When budget is CRITICAL, these requests trigger override:

| What you say | CRITICAL response |
|-------------|-------------------|
| "用 grok" / "用 kimi" | "Budget CRITICAL → force MiniMax" |
| "delegate 出去" / "派出去" | "Budget CRITICAL → no delegation" |
| "用貴嗰個" / "用好嗰個" | "Budget CRITICAL → only MiniMax available" |

### 🎯 Implicit Triggers (I check without you asking)

For **any work request**, I automatically:
1. Read `budget_status.md` (cached, no extra cost)
2. Score task complexity
3. Apply routing rules
4. Tell you my decision (model + delegate yes/no)

Example:
- You: "幫我分析下 TSLA"
- Me: "Complexity 3.1/10 | Budget HEALTHY → use kimi-k2.6, direct execution"

### 📝 Session Start Shortcuts

Start any session with these to activate budget awareness:

| Shortcut | Result |
|----------|--------|
| "Nexi ready" | Budget status + ready signal |
| "go" | Budget status + proceed |
| "status" | Full budget report |
| "check" | Quick budget check |

## How Detection Works

```
Your message → Pattern matcher
    │
    ├── Budget keywords → Load skill, show status
    ├── Model keywords → Load skill, recommend
    ├── Task request → Auto-score + auto-route
    └── Casual chat → Normal response
```

**No technical terms needed. Speak naturally in Cantonese or English.**

## Routing Rules (Hard-Coded)

| Budget State | Model Rule | Delegation Rule |
|-------------|-----------|-----------------|
| **CRITICAL** (≥$1.80) | Force MiniMax-M2.7 | Disable delegate_task |
| **WARNING** (≥$1.50) | Downgrade 1 tier | Limit subagents |
| **HEALTHY** (<$1.50) | Use complexity mapping | Normal rules |

## Domain-Based Overrides

Certain topics bypass normal complexity scoring and route directly to
specialist models (unless budget is CRITICAL):

| Domain | Trigger Keywords | Model | Fallback |
|--------|-----------------|-------|----------|
| **Stock/Trading** | 股票, trading, investment, TSLA, AAPL, 交易, 投資, portfolio, 策略, strategy, alpaca | **grok-4-1-fast-reasoning** | kimi-k2.6 |

> 用戶偏好：股票相關任務優先使用 grok 模型，因為 grok 更適合投資分析和交易決策。

## Model Fallback Chain

Every model has a fallback chain. If a model's API key is missing or the
provider is unavailable, the router automatically walks the chain:

```
grok-4-1-fast-reasoning → kimi-k2.6 → kimi-k2.5 → minimax-m2.7
kimi-k2.6               → kimi-k2.5 → minimax-m2.7
kimi-k2.5               → minimax-m2.7
deepseek-chat           → minimax-m2.7
minimax-m2.7            → (no fallback — ultimate safety net)
```

This prevents "No LLM provider configured" errors like the one that
caused gateway-self-heal to fail repeatedly.

## Complexity → Model Mapping

| Score | Level | Default Model | Delegate? |
|-------|-------|---------------|-----------|
| 0-1 | TRIVIAL | MiniMax-M2.7 / deepseek-chat* | No |
| 1-3 | LOW | MiniMax-M2.7 / deepseek-chat* | No |
| 3-5 | MEDIUM | kimi-k2.6 | Consider |
| 5-7 | HIGH | kimi-k2.6 | Yes |
| 7-9 | VERY_HIGH | grok-4-1-fast-reasoning | Yes |
| 9-10 | EXTREME | grok-4-1-fast-reasoning | Force |

> *During peak hours (14:00-18:00 HKT), simple tasks use deepseek-chat instead
> of MiniMax to avoid congestion. See Time-of-Day Routing below.

## Hybrid Complexity Scoring

The scorer uses a **two-layer approach** to minimize API cost:

### Layer 1: Rule-Based (FREE, ~80% coverage)
Fast-path detection using keyword triggers + length heuristics:
- **Simple triggers**: "係嗎", "幾時", "check", "status", "hello", "ok" → score 1.0
- **Complex triggers**: "寫個程式", "debug", "策略", "system design", "report" → score 8.0
- **Short prompts** (<80 chars, no triggers) → score 1.0
- **Long prompts** (≥500 chars) → skip to Layer 2

If Layer 1 returns a definite score, **no model inference is used**. Zero cost.

### Layer 2: Heuristic Analysis (boundary cases only)
For prompts that fall in the ambiguous zone (score 3-7), the full heuristic
analyzer runs: vocabulary richness, pattern matching, structural analysis.

```
Prompt → Layer 1 (rule-based)
    ├── Definite simple/complex → Return immediately (FREE)
    └── Boundary case → Layer 2 (heuristic)
```

## Time-of-Day Routing

To avoid MiniMax congestion during peak hours, the router checks the
**current HKT time** before selecting a model for simple tasks.

### Peak Hours: 14:00–18:00 HKT
| Complexity | Off-Peak Model | Peak Model |
|-----------|----------------|------------|
| 0-1 (TRIVIAL) | MiniMax-M2.7 | **deepseek-chat** |
| 1-3 (LOW) | MiniMax-M2.7 | **deepseek-chat** |
| 3-5 (MEDIUM) | kimi-k2.6 | kimi-k2.6 |
| 5+ | kimi-k2.6 / grok | (unchanged) |

> Budget overrides still take priority. If budget is CRITICAL during peak,
> the cheapest available model is forced regardless of time.

### Why This Matters
MiniMax-M2.7 is the cheapest option, but during 14:00-18:00 HKT it suffers
from congestion (slow responses, occasional failures). The system
automatically routes simple tasks to **deepseek-chat** during these hours
to maintain responsiveness without increasing cost significantly.

### Auto-Monitoring Peak Congestion

Instead of assuming peak hours are always 14:00-18:00, the system can
**auto-detect** when MiniMax congestion has cleared:

```bash
# Run a latency test (sends minimal prompt to MiniMax, measures response time)
python3 /home/sunnycsl/.hermes/scripts/decision_engine/minimax_peak_monitor.py

# Show last 7 days of latency stats
python3 /home/sunnycsl/.hermes/scripts/decision_engine/minimax_peak_monitor.py --summary
```

The monitor runs as a cron job every 30 minutes during peak hours:
- **Latency < 1.5s** for 3 consecutive checks → marks "peak cleared"
- **Latency > 3s** at any time → reactivates peak mode
- Results stored in `~/.hermes/data/minimax_peak_status.json`

When the monitor reports peak is cleared for several consecutive days,
update `rules.yaml` to remove or adjust `peak_model_mapping`.

### Cron Job Model Binding

**Cron jobs do NOT go through the Decision Engine.** They use **static model binding**—the model is fixed at creation time and never changes based on budget or time.

To keep cron jobs aligned with routing rules, bind them explicitly:

| Task Type | Recommended Model | Provider | Why |
|-----------|------------------|----------|-----|
| Daily budget update | minimax-m2.7 | minimax | Cheapest, runs off-peak |
| Instagram EV preview | minimax-m2.7 | minimax | Low complexity, off-peak |
| Stock research / trading | **grok-4-1-fast-reasoning** | **xai** | User preference: grok for all investment tasks |
| Trading execution | **grok-4-1-fast-reasoning** | **xai** | Critical decisions need best reasoning |
| System audit / check | minimax-m2.7 | minimax | Simple status checks |

#### Bulk-Update Cron Job Models

Hermes CLI (`hermes cron edit`) does **not** expose `--model` or `--provider` flags.
Use the internal Python API instead:

```python
import sys
sys.path.insert(0, '/home/sunnycsl/.hermes/hermes-agent')
from cron.jobs import get_job, update_job

# Update a single job
job = update_job("JOB_ID_HERE", {
    "model": "grok-4-1-fast-reasoning",
    "provider": "xai"
})

# Verify
print(job.get("model"), job.get("provider"))
```

> **No fallback for cron jobs.** If the bound provider fails (e.g. xai outage),
> the job fails. There is no automatic fallback to another provider.
> Monitor `last_status` in `cronjob(action="list")` and switch manually if needed.

## Files

| File | Purpose |
|------|---------|
| `scripts/decision_engine/metrics_api.py` | Query central_metrics.db |
| `scripts/decision_engine/complexity_scorer.py` | Score prompt complexity |
| `scripts/decision_engine/decision_router.py` | Core routing logic |
| `scripts/decision_engine/rules.yaml` | Tunable thresholds |
| `scripts/decision_engine/enable_for_session.py` | One-shot status output |
| `scripts/decision_engine/update_budget_status.py` | Cron updater (updates both budget_status.md + SKILL.md frontmatter) |
| `data/budget_status.md` | Live status cache |

## Manual Usage

```python
from decision_router import DecisionRouter

router = DecisionRouter()
decision = router.decide("Analyze TSLA earnings...")

print(decision.model)           # "kimi-k2.6"
print(decision.should_delegate) # True
print(decision.reasoning)       # ["Complexity: 3.1/10", ...]
```

## Cron Setup

```bash
# Update budget status every hour (updates both budget_status.md AND SKILL.md)
0 * * * * /usr/bin/python3 /home/sunnycsl/.hermes/scripts/decision_engine/update_budget_status.py
```

## Setup Verification Checklist

After initial setup, verify:
1. `cronjob list` shows the budget-update job
2. `~/.hermes/data/budget_status.md` exists and shows today's spend
3. Run `enable_for_session.py` manually to confirm output format
4. Check that SKILL.md frontmatter shows current budget state

## Threshold Tuning Notes (Learned from Testing)

- **Delegate threshold lowered to 3.0** (from 6.0) because microservices
  and trading analysis tasks scored only 2.0–3.0 on the heuristic scorer.
  Without this adjustment, they would never trigger subagent delegation.
- **Vocabulary weight raised to 0.30**, patterns to 0.25, length lowered
  to 0.15. Prevents long but simple prompts from scoring artificially high.

## Architecture Notes (Learned the Hard Way)

### ❌ Do NOT patch config.yaml
Initially the system patched `config.yaml` system_prompt to inject budget rules.
**This was wrong** — Hermes updates overwrite config.yaml, destroying the patch.
The correct approach: keep config.yaml pristine and inject live state into
**SKILL.md frontmatter** via the cron updater. The skill's YAML frontmatter
carries the live `budget_live` block; when the skill is loaded, the agent
sees current state without any system file modification.

### Frontmatter Injection Pattern
The cron script regenerates the YAML frontmatter with fresh data, then
replaces the old frontmatter in SKILL.md. The replacement must use
`content.split("---", 2)` to properly strip the **entire** old frontmatter
(both opening and closing `---`). Using `partition("---")` only strips the
first `---` and leaves a double frontmatter behind.

### Semi-Auto vs Full-Auto Configuration Adjustment
When building auto-adjustment features (e.g. peak hour routing rules),
prefer **semi-automatic** over **fully automatic** mutation of config files.
In this session, the peak monitor was originally designed to auto-rewrite
`rules.yaml` when congestion cleared. After discussion, the user rejected
full automation and requested a "human-in-the-loop" approach: the monitor
writes a recommendation file, and the human reviews and approves before
applying. This avoids silent configuration drift and maintains user trust.

### Auto-Load Limitation
Hermes has **no session auto-load mechanism for skills**. There is no config
option to say "load this skill at every session start". The agent must either:
- Be told explicitly to load the skill
- Run the enable script
- Read the status file

This is an architectural limitation, not a configuration issue.

## Pitfalls

1. **Budget status is cached ~1 hour** — rapid spending spikes may lag
2. **Complexity scoring is heuristic** — not perfect; tune rules.yaml for your domain
3. **CRITICAL mode disables all paid models AND subagents** — subagents double cost
4. **State is per-day reset** — budget counter resets at 00:00 UTC
5. **This skill does NOT auto-load** — Hermes has no session auto-load mechanism.
   You must explicitly load it, run enable_for_session.py, or read budget_status.md.
6. **Never patch config.yaml for live state injection** — use SKILL.md frontmatter
   via the cron updater instead. Config patches are destroyed by Hermes updates.
7. **Peak hour override is ignored when budget is CRITICAL** — the cheapest model
   is always forced regardless of time-of-day. This is intentional but can surprise
   users who expect deepseek-chat during peak hours even when over budget.
8. **Cron job model bindings are static** — they do NOT auto-adjust for peak hours
   unless the cron schedule itself falls outside peak. Bind wisely or use the
   decision engine's dynamic routing inside the cron prompt instead of a fixed model.
9. **Validate provider credentials exist before binding cron jobs.**
   Before setting `provider: "openrouter"` on any cron job, verify the provider
   is actually configured in the system. If the provider lacks valid credentials,
   every job using it will fail with "No LLM provider configured".
10. **Cron job provider/model edits must use the internal Python API, not the CLI.**
   The `hermes cron edit` command does NOT expose model or provider flags.
   Use `from cron.jobs import update_job` inside a Python script instead.
11. **Shell environment may not inherit variables from `.env` in cron contexts.**
   Scripts running as cron jobs should not rely solely on `os.getenv()` for
   configuration values. Read the configuration file directly as a fallback.
12. **Prefer "monitor + suggest + human approve" over silent auto-adjustment.**
   The peak monitor can auto-detect when MiniMax congestion has cleared and
   *could* rewrite `rules.yaml` automatically. However, silently mutating
   configuration files introduces stability risk and surprises the user.
   Recommended pattern: (a) monitor collects data, (b) writes a recommendation
   report, (c) human reviews and approves the change. Only auto-adjust after
   the user has explicitly opted in.

13. **Validate provider credentials exist before mass-updating cron job providers.**
   When bulk-binding cron jobs to a new provider, verify that the provider is
   actually configured with valid credentials first. Otherwise every job will
   fail with "No LLM provider configured" and trigger cascading self-heal loops.
   Check the provider's environment variable in `.env` before applying changes.

14. **Pass the raw prompt to the router's selection method for domain overrides.**
   The router must receive the original user prompt (not just the complexity
   score) to perform keyword-based domain overrides (e.g. detecting stock or
   trading terms and routing to the preferred investment model). If the prompt
   is not passed, domain overrides silently fail and the task routes to the
   default complexity-mapped model instead.

15. **Fallback chain checks key presence, not just model name.**
   The fallback resolver walks the chain but skips any model whose provider
   lacks valid credentials in the environment. This prevents configuration
   errors, but it also means the **effective** fallback chain may differ from
   the configured chain when credentials are missing. Log which model was
   actually chosen for transparency.

## Updating the Engine (Developer Workflow)

When modifying the decision engine, you MUST update all of these together:

| Component | File | What to update |
|-----------|------|----------------|
| Config | `rules.yaml` | Add new thresholds, model mappings, peak_model_mapping, hybrid_scoring config |
| Router | `decision_router.py` | Add routing logic (e.g. `_is_peak_hour`, `_select_model` changes) |
| Scorer | `complexity_scorer.py` | Add scoring methods (e.g. `score_hybrid`, `_score_rule_based`) |
| Docs | `SKILL.md` | Update routing tables, architecture notes, pitfalls |
| Cron Jobs | `cronjob update` | Re-bind models to align with new routing rules |

**Test after every change:**
```bash
cd /home/sunnycsl/.hermes/scripts/decision_engine
python3 -c "
from decision_router import DecisionRouter
router = DecisionRouter()
# Test off-peak
print('Off-peak:', router._is_peak_hour())
# Test peak (simulate)
router._is_peak_hour = lambda: True
# Run decision tests...
"
```

## When NOT to Use

- If you don't need cost tracking or model usage data
- If all your models are free (MiniMax only)
- If you want complete manual control over everything
