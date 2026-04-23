#!/usr/bin/env python3
"""
Enable Decision Engine for current Hermes session.

This script generates a dynamic system prompt snippet showing:
- Current budget status
- Today's model usage breakdown
- Real-time routing rules

Usage in Hermes system prompt or cron job:
    python3 ~/.hermes/scripts/decision_engine/enable_for_session.py

The output can be piped or read into the agent context.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from decision_router import DecisionRouter


def main():
    router = DecisionRouter()
    addon = router.get_system_prompt_addon()
    print(addon)

    # Also show current decision examples
    print("\n## 🧠 Example Routing Decisions")
    print("(How different tasks would be routed right now)")
    print()

    examples = [
        "你好",
        "Explain Python list comprehensions",
        "Write a Redis cache module with circuit breaker",
        "Analyze TSLA stock and provide trading strategy",
        "Refactor monolith to microservices with K8s deployment",
    ]

    for ex in examples:
        d = router.decide(ex)
        deleg = f"[→{d.delegate_mode}]" if d.should_delegate else "[direct]"
        print(f"  {deleg:<12} {d.model:<22} | {ex[:40]}")


if __name__ == "__main__":
    main()
