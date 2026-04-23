# Hermes Decision Engine

> ⚠️ **AUTO ROUTING DISABLED (2026-04-23)** — Data collection/monitoring only. All model selection is now manual. Cost data still tracked.

A cost-aware model routing system for [Hermes Agent](https://github.com/nousresearch/hermes-agent). Scores prompt complexity, monitors daily budget spend, and routes tasks to the optimal model — or logs decisions for manual review.

## Features

- **Hybrid Complexity Scoring** — Rule-based (free) + MiniMax heuristic for boundary cases
- **Live Budget Tracking** — Queries `central_metrics.db` for real-time cost visibility
- **Time-of-Day Routing** — Avoids MiniMax peak congestion (14:00–18:00 HKT)
- **Domain Overrides** — Stock/trading tasks route to grok by keyword detection
- **Model Fallback Chain** — Automatic failover when providers are unavailable
- **SKILL.md Frontmatter Injection** — Live state carried in skill YAML for zero-cost context loading

## Architecture

```
User Prompt → ComplexityScorer (0-10) + MetricsAPI ($ today)
                    ↓
         DecisionRouter → (model, delegate?, reasoning)
                    ↓
              Execute with chosen strategy
```

## Installation

### 1. Copy scripts to your Hermes scripts directory

```bash
mkdir -p ~/.hermes/scripts/decision_engine
cp -r scripts/* ~/.hermes/scripts/decision_engine/
```

### 2. Copy config

```bash
cp config/rules.yaml ~/.hermes/scripts/decision_engine/rules.yaml
```

### 3. Set up hourly budget cron

```bash
# Edit crontab
crontab -e

# Add this line:
0 * * * * /usr/bin/python3 ~/.hermes/scripts/decision_engine/update_budget_status.py
```

### 4. Verify installation

```bash
python3 ~/.hermes/scripts/decision_engine/enable_for_session.py
```

You should see current budget status and example routing decisions.

## Configuration

Edit `~/.hermes/scripts/decision_engine/rules.yaml` to tune:

| Section | What to adjust |
|---------|----------------|
| `cost_budget.daily_limit` | Daily USD budget before forcing cheapest model |
| `cost_budget.critical_threshold` | Hard cap — all paid models blocked above this |
| `time_of_day.peak_hours` | HKT hours when MiniMax is unreliable |
| `domain_overrides` | Keywords that force specific models |
| `complexity.delegate_threshold` | Complexity score that triggers subagent delegation |
| `hybrid_scoring.boundary` | When to call MiniMax for precise scoring |

## Usage

### In your skill or agent prompt

Load the skill to get live budget state injected via YAML frontmatter:

```
/skill decision-engine
```

### Programmatic usage

```python
import sys
sys.path.insert(0, '~/.hermes/scripts/decision_engine')

from decision_router import DecisionRouter

router = DecisionRouter()
decision = router.decide("Analyze TSLA earnings report and suggest a trading strategy")

print(f"Model: {decision.model}")
print(f"Delegate: {decision.should_delegate}")
print(f"Reasoning: {decision.reasoning}")
print(f"Today's spend: ${decision.budget_status.today_cost:.2f}")
```

### CLI one-shot status

```bash
python3 ~/.hermes/scripts/decision_engine/enable_for_session.py
```

## Files

| File | Purpose |
|------|---------|
| `scripts/decision_router.py` | Core routing logic |
| `scripts/complexity_scorer.py` | Hybrid complexity scoring |
| `scripts/metrics_api.py` | Central metrics DB query |
| `scripts/minimax_peak_monitor.py` | Latency monitoring during peak hours |
| `scripts/update_budget_status.py` | Cron job — updates status cache + SKILL frontmatter |
| `scripts/enable_for_session.py` | CLI status output |
| `scripts/rules.yaml` | All tunable thresholds and model configs |
| `config/rules.yaml` | Same rules.yaml (Git-safe copy) |

## Model Fallback Chain

```
grok-4-1-fast-reasoning → kimi-k2.6 → kimi-k2.5 → minimax-m2.7
kimi-k2.6               → kimi-k2.5 → minimax-m2.7
deepseek-chat           → minimax-m2.7
minimax-m2.7            → (no fallback — ultimate safety net)
```

## Budget States

| State | Threshold | Behavior |
|-------|-----------|----------|
| HEALTHY | < $1.50/day | Normal routing rules apply |
| WARNING | ≥ $1.50/day | Downgrade one tier |
| CRITICAL | ≥ $1.80/day | Force MiniMax only, disable delegation |

## Limitations

- **Auto routing is disabled.** The system collects cost data but does not automatically select models. You control all routing manually.
- Cron jobs use **static model binding** — they do not adapt to budget state.
- Budget status is cached ~1 hour. Rapid spending spikes may not be reflected immediately.
- Complexity scoring is heuristic — tune `rules.yaml` for your domain.

## License

MIT — SunnyCSL
