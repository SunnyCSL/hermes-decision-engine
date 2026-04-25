#!/usr/bin/env python3
"""
Update live budget status file for Hermes auto-injection.

Run via cron every hour:
    0 * * * * python3 ~/.hermes/scripts/decision_engine/update_budget_status.py

Outputs to ~/.hermes/data/budget_status.md
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from decision_router import DecisionRouter


def main():
    router = DecisionRouter()
    addon = router.get_system_prompt_addon()

    # 1. Update budget status markdown cache
    # Try script-local data dir first, fall back to Hermes default
    local_data = Path(__file__).parent.parent.parent / "data"
    hermes_data = Path.home() / ".hermes" / "data"
    output_dir = local_data if local_data.exists() else hermes_data
    output_path = output_dir / "budget_status.md"
    output_path.write_text(addon, encoding="utf-8")
    print(f"Updated: {output_path}")

    # 2. Sync into SKILL.md frontmatter so skill auto-loads with live data
    # Try script-local skill dir first, fall back to Hermes default
    local_skill = Path(__file__).parent.parent.parent / "skills" / "decision-engine" / "SKILL.md"
    hermes_skill = Path.home() / ".hermes" / "skills" / "decision-engine" / "SKILL.md"
    skill_path = local_skill if local_skill.exists() else hermes_skill
    if skill_path.exists():
        _sync_skill_frontmatter(skill_path, router)
        print(f"Updated: {skill_path}")


def _sync_skill_frontmatter(skill_path: Path, router: DecisionRouter) -> None:
    """Inject live budget state into SKILL.md YAML frontmatter."""
    # If auto routing disabled, use simple monitoring format
    if not router.config.get("routing", {}).get("enabled", True):
        _sync_skill_frontmatter_monitoring(skill_path, router)
        return

    budget = router.metrics.get_budget_status()
    model_usage = router.metrics.get_model_usage_today()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    usage_lines = "\n".join(
        f"    - {mu.model}: {mu.requests} req, {mu.total_tokens:,} tok, ${mu.cost_usd:.2f}"
        for mu in model_usage[:3]
    )

    frontmatter = f"""---
name: decision-engine
version: "1.1"
description: >
  ⚠️ AUTO ROUTING DISABLED (2026-04-23) — Data collection/monitoring only.
  All model selection is now manual. Cost data still tracked.
budget_live:
  today_cost: {budget.today_cost:.2f}
  budget_limit: {budget.budget_limit:.2f}
  percent_used: {budget.percent_used:.0f}
  status: MONITORING
  routing_mode: DISABLED
  updated_at: "{now}"
trigger:
  - "manual check: run 'cat ~/.hermes/data/budget_status.md'"
  - "when user asks about cost or model recommendation"
---
"""

    content = skill_path.read_text(encoding="utf-8")
    # Strip old frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            rest = parts[2].lstrip("\n")
        else:
            rest = content
    else:
        rest = content

    skill_path.write_text(frontmatter + "\n" + rest, encoding="utf-8")


def _sync_skill_frontmatter_monitoring(skill_path: Path, router: DecisionRouter) -> None:
    """When routing is disabled, inject minimal monitoring-only frontmatter."""
    budget = router.metrics.get_budget_status()
    model_usage = router.metrics.get_model_usage_today()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    usage_lines = "\n".join(
        f"    - {mu.model}: {mu.requests} req, {mu.total_tokens:,} tok, ${mu.cost_usd:.2f}"
        for mu in model_usage[:3]
    )

    frontmatter = f"""---
name: decision-engine
version: "1.1"
description: >
  ⚠️ AUTO ROUTING DISABLED (2026-04-23) — Data collection/monitoring only.
  All model selection is now manual. Cost data still tracked.
budget_live:
  today_cost: {budget.today_cost:.2f}
  budget_limit: {budget.budget_limit:.2f}
  percent_used: {budget.percent_used:.0f}
  status: MONITORING
  routing_mode: DISABLED
  updated_at: "{now}"
  top_models_today:
{usage_lines}
trigger:
  - "manual check: run 'cat ~/.hermes/data/budget_status.md'"
  - "when user asks about cost or model recommendation"
---
"""

    content = skill_path.read_text(encoding="utf-8")
    # Strip old frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            rest = parts[2].lstrip("\n")
        else:
            rest = content
    else:
        rest = content

    skill_path.write_text(frontmatter + "\n" + rest, encoding="utf-8")


if __name__ == "__main__":
    main()
