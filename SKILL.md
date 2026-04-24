---
name: decision-engine
version: "1.2"
date: "2026-04-25"
description: >
  ⚠️ AUTO ROUTING DISABLED (2026-04-23) — Data collection/monitoring only.
  All model selection is now manual. Cost data still tracked.
budget_live:
  today_cost: 0.00
  budget_limit: 10.00
  percent_used: 0
  status: UNKNOWN
  routing_mode: DISABLED
  updated_at: "2026-04-25"
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

## Architecture Overview

```
User Prompt → ComplexityScorer (0-10) + MetricsAPI ($ today)
                    ↓
         DecisionRouter → (model, delegate?, reasoning)
                    ↓
              Execute with chosen strategy
```

## Files

| File | Purpose |
|------|---------|
| `scripts/metrics_api.py` | Query central_metrics.db |
| `scripts/complexity_scorer.py` | Score prompt complexity |
| `scripts/decision_router.py` | Core routing logic |
| `config/rules.yaml` | Tunable thresholds |
| `scripts/enable_for_session.py` | One-shot status output |
| `scripts/update_budget_status.py` | Cron updater |
| `scripts/minimax_peak_monitor.py` | Peak hour congestion monitor |
| `~/.hermes/data/budget_status.md` | Live status cache |

## Routing Rules

| Budget State | Model Rule | Delegation Rule |
|-------------|-----------|-----------------|
| **CRITICAL** (≥$1.80) | Force MiniMax-M2.7 | Disable delegate_task |
| **WARNING** (≥$1.50) | Downgrade 1 tier | Limit subagents |
| **HEALTHY** (<$1.50) | Use complexity mapping | Normal rules |

## Model Fallback Chain

```
grok-4-1-fast-reasoning → kimi-k2.6 → kimi-k2.5 → minimax-m2.7
kimi-k2.6               → kimi-k2.5 → minimax-m2.7
kimi-k2.5               → minimax-m2.7
deepseek-chat           → minimax-m2.7
minimax-m2.7            → (no fallback — ultimate safety net)
```

## Complexity → Model Mapping

| Score | Level | Default Model | Delegate? |
|-------|-------|---------------|-----------|
| 0-1 | TRIVIAL | MiniMax-M2.7 | No |
| 1-3 | LOW | MiniMax-M2.7 | No |
| 3-5 | MEDIUM | kimi-k2.6 | Consider |
| 5-7 | HIGH | kimi-k2.6 | Yes |
| 7-9 | VERY_HIGH | grok-4-1-fast-reasoning | Yes |
| 9-10 | EXTREME | grok-4-1-fast-reasoning | Force |

## Domain-Based Overrides

Certain topics bypass normal complexity scoring:

| Domain | Keywords | Model | Fallback |
|--------|----------|-------|---------|
| **Stock/Trading** | stock, trading, investment, TSLA, AAPL, 股票, 交易, 投資, alpaca | **grok-4-1-fast-reasoning** | kimi-k2.6 |

## Hybrid Complexity Scoring

### Layer 1: Rule-Based (FREE, ~80% coverage)
- **Simple triggers** ("係嗎", "check", "hello") → score 1.0
- **Complex triggers** ("寫個程式", "debug", "策略") → score 8.0
- **Short prompts** (<80 chars) → score 1.0
- **Long prompts** (≥500 chars) → at least medium

### Layer 2: Heuristic Analysis (boundary cases only)
For ambiguous prompts (score 3-7), runs vocabulary/pattern analysis.

## Time-of-Day Routing

Peak hours: 14:00–18:00 HKT — MiniMax may have congestion.

| Complexity | Off-Peak Model | Peak Model |
|-----------|----------------|------------|
| 0-1 (TRIVIAL) | MiniMax-M2.7 | **deepseek-chat** |
| 1-3 (LOW) | MiniMax-M2.7 | **deepseek-chat** |
| 3-5 (MEDIUM) | kimi-k2.6 | kimi-k2.6 |

> Budget CRITICAL overrides peak routing — cheapest model forced regardless of time.

## Cron Setup

```bash
# Update budget status every hour
0 * * * * /usr/bin/python3 ~/.hermes/scripts/decision_engine/update_budget_status.py
```

## Session Start Protocol

**Every new session should check budget before model selection:**

```bash
# Option A: Run enable script
python3 ~/.hermes/scripts/decision_engine/enable_for_session.py

# Option B: Read status file
cat ~/.hermes/data/budget_status.md

# Option C: Load this skill
skill_view("decision-engine")
```

## Manual Usage

```python
import sys
sys.path.insert(0, '~/.hermes/scripts/decision_engine')

from decision_router import DecisionRouter

router = DecisionRouter()
decision = router.decide("Analyze TSLA earnings...")

print(decision.model)           # "kimi-k2.6"
print(decision.should_delegate)  # True
print(decision.reasoning)       # ["Complexity: 3.1/10", ...]
```

## Threshold Tuning Notes

- **Delegate threshold: 3.0** (lowered from 6.0 for microservices/trading tasks)
- **Vocabulary weight: 0.30, patterns: 0.25, length: 0.15**

## Architecture Notes

### Do NOT patch config.yaml
Initial versions patched `config.yaml` for live state — **wrong approach**.
Hermes updates overwrite config.yaml, destroying the patch.
**Correct approach**: inject live state into **SKILL.md frontmatter** via cron updater.

### Frontmatter Injection Pattern
The cron script regenerates YAML frontmatter with fresh data, replaces old frontmatter
using `content.split("---\", 2)` to strip entire block (both opening and closing `---`).

## Pitfalls

1. Budget status cached ~1 hour — rapid spikes may lag
2. Complexity scoring is heuristic — tune rules.yaml for your domain
3. CRITICAL mode disables all paid models AND subagents
4. State resets at 00:00 UTC
5. This skill does NOT auto-load — must explicitly load or run enable script
6. Never patch config.yaml — use SKILL.md frontmatter
7. Peak hour override ignored when budget is CRITICAL
8. Cron job model bindings are static
9. Validate provider credentials before binding cron jobs
10. Shell env may not inherit .env in cron contexts

## When NOT to Use

- If you don't need cost tracking or model usage data
- If all your models are free
- If you want complete manual control
