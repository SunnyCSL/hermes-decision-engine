# Hermes Decision Engine

AI model cost-aware routing system for Hermes Agent. Monitors daily spending and routes tasks to appropriate models based on complexity and budget.

**⚠️ STATUS: Auto routing DISABLED (2026-04-23)** — Now data collection/monitoring only. All model selection is manual.

## Features

- **Cost Tracking**: Real-time monitoring of daily token usage per model
- **Complexity Scoring**: Hybrid 0-10 scale (rule-based + heuristic)
- **Model Fallback Chains**: Automatic failover when providers fail
- **Peak Hour Routing**: Avoids MiniMax congestion during 14:00-18:00 HKT
- **Domain Overrides**: Stock/trading tasks route to grok by preference
- **SKILL.md Integration**: Live budget state injected into skill frontmatter

## Installation

### 1. Clone or Copy to Your Hermes Workspace

```bash
# Copy scripts to your Hermes scripts directory
cp -r scripts ~/.hermes/scripts/decision_engine
cp config/rules.yaml ~/.hermes/scripts/decision_engine/rules.yaml

# Copy skill
cp SKILL.md ~/.hermes/skills/decision-engine/SKILL.md
```

### 2. Set Up Database Path

Ensure `~/.hermes/data/central_metrics.db` exists (created by Hermes metrics collection).

### 3. Configure Cron Job

Add to crontab — updates budget status every hour:
```
0 * * * * /usr/bin/python3 ~/.hermes/scripts/decision_engine/update_budget_status.py
```

### 4. Install Dependencies

```bash
pip install pyyaml
```

## Configuration

Edit `config/rules.yaml` to customize:

- **Cost thresholds**: `cost_budget.daily_limit`, `warning_threshold`, `critical_threshold`
- **Peak hours**: `time_of_day.peak_hours.start` / `.end`
- **Model mapping**: `complexity.model_mapping`
- **Domain overrides**: `domain_overrides.stock.keywords`

## Usage

### Check Budget Status

```bash
python3 ~/.hermes/scripts/decision_engine/enable_for_session.py
```

### Programmatic Usage

```python
import sys
sys.path.insert(0, '~/.hermes/scripts/decision_engine')

from decision_router import DecisionRouter
from metrics_api import MetricsAPI

# Get current budget
api = MetricsAPI()
budget = api.get_budget_status()
print(f"Today: ${budget.today_cost:.2f} / ${budget.budget_limit:.2f}")

# Route a task
router = DecisionRouter()
decision = router.decide("Analyze Tesla stock and create a trading plan")

print(f"Model: {decision.model}")
print(f"Delegate: {decision.should_delegate}")
for reason in decision.reasoning:
    print(f"  - {reason}")
```

### Peak Hour Monitoring

```bash
# Run latency test
python3 ~/.hermes/scripts/decision_engine/minimax_peak_monitor.py

# View last 7 days summary
python3 ~/.hermes/scripts/decision_engine/minimax_peak_monitor.py --summary
```

## File Structure

```
hermes-decision-engine/
├── SKILL.md              # Hermes skill with live budget in frontmatter
├── README.md             # This file
├── scripts/
│   ├── decision_router.py      # Core routing logic
│   ├── complexity_scorer.py    # 0-10 complexity scoring
│   ├── metrics_api.py          # DB cost queries
│   ├── rules.yaml              # Tunable config
│   ├── enable_for_session.py   # One-shot status
│   ├── update_budget_status.py # Cron updater
│   ├── minimax_peak_monitor.py # Congestion monitor
│   └── __init__.py
└── config/
    └── rules.yaml        # Alias for scripts/rules.yaml
```

## Routing Logic

1. **Check budget status** → CRITICAL/WARNING/HEALTHY
2. **Score prompt complexity** → 0-10 scale
3. **Apply domain override** if stock/trading keywords detected
4. **Apply time-of-day override** during peak hours (14:00-18:00 HKT)
5. **Map complexity to model** using `complexity.model_mapping`
6. **Check fallback chain** if primary model unavailable
7. **Decide delegation** based on complexity threshold

## Model Fallback Chain

```
grok-4-1-fast-reasoning → kimi-k2.6 → kimi-k2.5 → minimax-m2.7
kimi-k2.6               → kimi-k2.5 → minimax-m2.7
kimi-k2.5               → minimax-m2.7
deepseek-chat            → minimax-m2.7
minimax-m2.7            → (end of chain)
```

## Cost Thresholds (USD/day)

| Status | Threshold | Action |
|--------|-----------|--------|
| HEALTHY | < $1.50 | Normal routing |
| WARNING | ≥ $1.50 | Downgrade 1 tier |
| CRITICAL | ≥ $1.80 | Force MiniMax, disable delegation |

## Troubleshooting

### "No LLM provider configured"
- Check provider credentials in `.env`
- Verify fallback chain models have valid credentials

### Budget status not updating
- Check cron job: `cronjob list`
- Verify script path: `~/.hermes/scripts/decision_engine/update_budget_status.py`

### High latency during peak hours
- Run peak monitor: `python3 ~/.hermes/scripts/decision_engine/minimax_peak_monitor.py`
- Consider adding deepseek-chat as MiniMax fallback

## License

MIT — SunnyCSL
