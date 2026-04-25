# Hermes Decision Engine

Cost-aware task routing + real-time budget monitoring for [Hermes Agent](https://github.com/nousresearch/hermes-agent).

Routes tasks to optimal models (MiniMax → Kimi → Grok) based on:
- **Prompt complexity** (0–10 scoring via hybrid rule-based + heuristic analysis)
- **Budget status** (daily cost vs. limit)
- **Time-of-day** (peak hour avoidance for MiniMax)
- **Domain overrides** (stock/trading → Grok, regardless of complexity)

## ⚠️ Status

Auto-routing is **currently disabled** (2026-04-23). The system operates in data-collection + monitoring mode only. All model selection is manual. Cost data is still tracked and displayed.

## Repository Structure

```
hermes-decision-engine/
├── SKILL.md                    # Hermes skill with routing rules & documentation
├── README.md                   # This file
├── scripts/
│   ├── decision_router.py      # Core routing brain
│   ├── complexity_scorer.py    # Hybrid complexity scoring (rule-based + heuristic)
│   ├── metrics_api.py          # Real-time cost/token query from SQLite
│   ├── minimax_peak_monitor.py # MiniMax congestion auto-detection
│   ├── update_budget_status.py # Cron: update budget_status.md + SKILL.md frontmatter
│   ├── enable_for_session.py   # One-shot session enable script
│   └── __init__.py
└── config/
    └── rules.yaml              # All tunable thresholds, model configs, keywords
```

## Installation

### 1. Copy to your Hermes workspace

```bash
# Copy scripts
cp -r scripts/decision_engine/* ~/.hermes/scripts/decision_engine/

# Copy skill
cp SKILL.md ~/.hermes/skills/decision-engine/SKILL.md

# Copy config
cp config/rules.yaml ~/.hermes/scripts/decision_engine/rules.yaml
```

### 2. Ensure the metrics database exists

The engine reads from `~/.hermes/data/central_metrics.db` (metrics_log table).

```bash
ls ~/.hermes/data/central_metrics.db
```

If missing, create it:

```sql
CREATE TABLE IF NOT EXISTS metrics_log (
    timestamp TEXT,
    component TEXT,
    model TEXT,
    provider TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    duration_sec REAL,
    cost_usd REAL,
    status TEXT
);
```

### 3. Set up cron job for hourly budget updates

```bash
# Add to crontab:
0 * * * * /usr/bin/python3 ~/.hermes/scripts/decision_engine/update_budget_status.py
```

This updates:
- `~/.hermes/data/budget_status.md` — live status cache
- `~/.hermes/skills/decision-engine/SKILL.md` frontmatter — auto-injected live state

## Usage

### Quick enable (at session start)

```python
# In a Hermes prompt or cron job:
python3 ~/.hermes/scripts/decision_engine/enable_for_session.py
```

Outputs current budget status + 5 example routing decisions.

### Manual routing decision

```python
import sys
sys.path.insert(0, '~/.hermes/scripts/decision_engine')

from decision_router import DecisionRouter

router = DecisionRouter()
decision = router.decide("Analyze TSLA earnings and suggest a trading strategy")

print(decision.model)           # "grok-4-1-fast-reasoning"
print(decision.should_delegate) # True
print(decision.reasoning)       # ["Complexity: 6.8/10", "Budget: healthy", ...]
```

### Check budget status

```bash
cat ~/.hermes/data/budget_status.md
```

### MiniMax peak congestion monitor

```bash
# Single latency test
python3 ~/.hermes/scripts/decision_engine/minimax_peak_monitor.py

# Summary of last 7 days
python3 ~/.hermes/scripts/decision_engine/minimax_peak_monitor.py --summary
```

## Configuration

All tunable parameters are in `config/rules.yaml`:

| Section | What to tune |
|---------|-------------|
| `cost_budget.daily_limit` | Daily USD budget |
| `complexity.delegate_threshold` | Complexity score to trigger delegation |
| `domain_overrides.stock.keywords` | Keywords that force Grok for trading tasks |
| `time_of_day.peak_hours` | HKT window to avoid MiniMax |
| `models` | Model pricing, fallback chains, capabilities |

## Routing Rules Summary

| Budget State | Model Rule | Delegation |
|-------------|-----------|-----------|
| **CRITICAL** (≥$9.00) | Force MiniMax-M2.7 | Disabled |
| **WARNING** (≥$8.00) | Downgrade 1 tier | Limited |
| **HEALTHY** (<$8.00) | Use complexity mapping | Normal |

| Complexity | Default Model |
|------------|--------------|
| 0–1 (TRIVIAL) | MiniMax-M2.7 |
| 1–3 (LOW) | MiniMax-M2.7 |
| 3–5 (MEDIUM) | kimi-k2.6 |
| 5–7 (HIGH) | kimi-k2.6 + delegate |
| 7–9 (VERY_HIGH) | grok-4-1-fast-reasoning + delegate |
| 9–10 (EXTREME) | grok-4-1-fast-reasoning + force delegate |

## Domain Overrides

Stock/trading/investment keywords always route to **grok-4-1-fast-reasoning** (unless budget critical):

```
stock, trading, investment, portfolio, alpaca, TSLA, AAPL, NVDA,
equity, option, margin, order, position, strategy, technical analysis,
股票, 交易, 投資, 持倉, 下單, 策略, 技術分析, ...
```

## Peak Hours (14:00–18:00 HKT)

During peak hours, simple tasks (complexity < 5) avoid MiniMax and route to **deepseek-chat** instead.

Peak detection is automatic — the `minimax_peak_monitor.py` script runs every 30 minutes during peak and measures actual latency. If MiniMax is consistently fast (<1.5s), peak mode is marked cleared.

## Files Reference

| File | Purpose |
|------|---------|
| `decision_router.py` | Core routing logic |
| `complexity_scorer.py` | Hybrid complexity scoring |
| `metrics_api.py` | Query `central_metrics.db` for real cost data |
| `minimax_peak_monitor.py` | Latency auto-detection |
| `update_budget_status.py` | Hourly cron script (updates `budget_status.md` + SKILL.md) |
| `enable_for_session.py` | One-shot status output |
| `rules.yaml` | All tunable configuration |
| `SKILL.md` | Hermes skill with live frontmatter injection |

## License

MIT — SunnyCSL
