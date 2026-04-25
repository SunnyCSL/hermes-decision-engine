"""
Hermes Decision Engine — Decision Router

The core brain: combines ComplexityScorer + MetricsAPI → outputs
(model choice, delegation decision, cost estimate, reasoning).

Usage:
    from decision_router import DecisionRouter
    router = DecisionRouter()
    decision = router.decide("Implement a Redis cache layer...")
    print(decision.model)          # "kimi-k2.6"
    print(decision.should_delegate) # True
    print(decision.reasoning)      # ["Complexity: 6.8/10", "Budget: healthy", ...]
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Any

import yaml

from metrics_api import MetricsAPI, BudgetStatus
from complexity_scorer import ComplexityScorer, ComplexityResult, TaskContext

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Final routing decision for a task."""
    prompt_preview: str
    complexity: ComplexityResult
    budget: BudgetStatus
    model: str                    # e.g. "kimi-k2.6"
    provider: str                 # e.g. "kimi-coding"
    should_delegate: bool
    delegate_mode: Optional[str]  # "parallel" | "single" | None
    estimated_cost_usd: float
    estimated_tokens: int
    reasoning: List[str]
    fallback_model: Optional[str] = None
    force_cheap: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_preview": self.prompt_preview[:80],
            "complexity_score": self.complexity.score,
            "complexity_level": self.complexity.level.name,
            "budget_status": self.budget.status,
            "today_cost": self.budget.today_cost,
            "model": self.model,
            "provider": self.provider,
            "should_delegate": self.should_delegate,
            "delegate_mode": self.delegate_mode,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_tokens": self.estimated_tokens,
            "reasoning": self.reasoning,
            "fallback_model": self.fallback_model,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def summary_line(self) -> str:
        """One-line summary for logging."""
        d = "[D]" if self.should_delegate else "[S]"
        return (
            f"{d} {self.model:<22} | complexity={self.complexity.score:.1f} | "
            f"budget={self.budget.status:<7} | ${self.estimated_cost_usd:.4f} | "
            f"{self.prompt_preview[:40]}"
        )


class DecisionRouter:
    """
    Cost-aware task router for Hermes Agent.

    Analyzes every incoming task and decides:
    1. Which model to use (MiniMax free → Kimi cheap → Grok expensive)
    2. Whether to delegate to subagents
    3. Estimated cost before execution
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        metrics_api: Optional[MetricsAPI] = None,
        complexity_scorer: Optional[ComplexityScorer] = None,
    ):
        self.config_path = config_path or (
            Path(__file__).parent / "rules.yaml"
        )
        self.config = self._load_config()
        self.metrics = metrics_api or MetricsAPI()
        self.scorer = complexity_scorer or ComplexityScorer()

        # Cache config values
        self.models_config = self.config.get("models", {})
        self.complexity_cfg = self.config.get("complexity", {})
        self.delegation_cfg = self.config.get("delegation", {})
        self.token_cfg = self.config.get("token_estimation", {})
        self.log_decisions = self.config.get("logging", {}).get("log_decisions", True)

    def _load_config(self) -> Dict[str, Any]:
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Config load failed: {e}")
        return {}

    def decide(
        self,
        prompt: str,
        context: Optional[TaskContext] = None,
        force_model: Optional[str] = None,
        no_delegate: bool = False,
    ) -> RoutingDecision:
        """
        Make a routing decision for a task.

        Args:
            prompt: The user's request text
            context: Optional task context
            force_model: Override model selection (e.g. user specified)
            no_delegate: Force no delegation even if complexity is high

        Returns:
            RoutingDecision with all routing parameters
        """
        reasoning: List[str] = []

        # 1. Score complexity (hybrid: rule-based free + heuristic fallback)
        complexity = self.scorer.score_hybrid(prompt, context)
        reasoning.append(f"Complexity: {complexity.score:.1f}/10 ({complexity.level.name})")

        # 2. Check budget
        budget = self.metrics.get_budget_status()
        reasoning.append(
            f"Budget: {budget.status} | today=${budget.today_cost:.2f} | "
            f"remaining=${budget.budget_remaining:.2f}"
        )

        # 3. Estimate tokens
        estimated_tokens = self._estimate_tokens(prompt)
        reasoning.append(f"Estimated tokens: {estimated_tokens:,}")

        # 4. Select model
        if force_model and force_model in self.models_config:
            model_key = force_model
            reasoning.append(f"Model: {model_key} (forced)")
        else:
            model_key = self._select_model(complexity, budget, estimated_tokens, prompt)
            reasoning.append(f"Model: {model_key} (auto-selected)")

        model_cfg = self.models_config.get(model_key, {})
        provider = model_cfg.get("provider", "unknown")

        # 5. Decide delegation
        should_delegate, delegate_mode = self._decide_delegation(
            complexity, budget, estimated_tokens, no_delegate, prompt
        )
        if should_delegate:
            reasoning.append(f"Delegate: {delegate_mode} subagent(s)")
        else:
            reasoning.append("Delegate: no (direct execution)")

        # 6. Estimate cost
        # Assume output = 2x input for estimate
        est_cost = self.metrics.estimate_request_cost(
            model_key, estimated_tokens, estimated_tokens * 2
        )
        reasoning.append(f"Estimated cost: ${est_cost:.4f}")

        # 7. Fallback
        fallback = None
        if budget.is_critical and model_key != self.metrics.get_cheapest_available_model():
            fallback = self.metrics.get_cheapest_available_model()
            reasoning.append(f"Fallback: {fallback} (budget critical)")

        decision = RoutingDecision(
            prompt_preview=prompt[:200],
            complexity=complexity,
            budget=budget,
            model=model_key,
            provider=provider,
            should_delegate=should_delegate,
            delegate_mode=delegate_mode,
            estimated_cost_usd=est_cost,
            estimated_tokens=estimated_tokens,
            reasoning=reasoning,
            fallback_model=fallback,
            force_cheap=budget.is_critical,
        )

        if self.log_decisions:
            logger.info(decision.summary_line())

        return decision

    def _select_model(
        self, complexity: ComplexityResult, budget: BudgetStatus, estimated_tokens: int, prompt: str = ""
    ) -> str:
        """Select model based on complexity + time-of-day + budget + domain overrides."""
        mapping = self.complexity_cfg.get("model_mapping", {})
        peak_mapping = self.complexity_cfg.get("peak_model_mapping", {})
        score = complexity.score

        # 1. Budget overrides (highest priority)
        if budget.is_critical:
            return self._resolve_with_fallback(self.metrics.get_cheapest_available_model())
        elif budget.is_warning:
            if score >= 7:
                return self._resolve_with_fallback(mapping.get("high", "kimi-k2.6"))
            elif score >= 5:
                return self._resolve_with_fallback(mapping.get("medium", "kimi-k2.5"))
            else:
                return self._resolve_with_fallback(mapping.get("low", "minimax-m2.7"))

        # 2. Domain overrides (stock/trading → grok regardless of complexity)
        if self._is_stock_related(prompt):
            return self._resolve_with_fallback("grok-4-1-fast-reasoning")

        # 3. Time-of-day override (only for simple tasks during peak hours)
        if self._is_peak_hour() and score < 5 and peak_mapping:
            # Simple task during peak → use peak mapping (avoids MiniMax)
            if score >= 3:
                return self._resolve_with_fallback(peak_mapping.get("medium", "kimi-k2.6"))
            elif score >= 1:
                return self._resolve_with_fallback(peak_mapping.get("low", "deepseek-chat"))
            else:
                return self._resolve_with_fallback(peak_mapping.get("trivial", "deepseek-chat"))

        # 4. Normal complexity-based selection
        if score >= 9:
            preferred = mapping.get("extreme", "grok-4-1-fast-reasoning")
        elif score >= 7:
            preferred = mapping.get("very_high", "grok-4-1-fast-reasoning")
        elif score >= 5:
            preferred = mapping.get("high", "kimi-k2.6")
        elif score >= 3:
            preferred = mapping.get("medium", "kimi-k2.6")
        else:
            preferred = mapping.get("low", "minimax-m2.7")

        return self._resolve_with_fallback(preferred)

    def _resolve_with_fallback(self, model_key: str) -> str:
        """
        Walk the fallback chain until we find a model whose API key is present.
        Prevents routing to models with missing credentials.
        """
        max_depth = self.config.get("retry", {}).get("fallback_chain_max_depth", 3)
        visited = set()
        current = model_key

        while current and current not in visited:
            if len(visited) >= max_depth:
                break
            visited.add(current)

            cfg = self.models_config.get(current, {})
            env_key = cfg.get("env_key")

            if not env_key:
                # No env key declared — assume available (legacy compat)
                return current

            if os.getenv(env_key, ""):
                return current

            # Try .env file as fallback
            env_path = Path.home() / ".hermes" / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith(f"{env_key}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val != "***" and val != "[REDACTED]":
                            return current
                        break

            # API key missing — follow fallback chain
            current = cfg.get("fallback")

        # Ultimate fallback: cheapest model that we know exists
        return "minimax-m2.7"

    def _is_stock_related(self, prompt: str) -> bool:
        """Check if prompt is stock/trading/investment related."""
        domain_cfg = self.config.get("domain_overrides", {}).get("stock", {})
        keywords = domain_cfg.get("keywords", [])
        if not keywords:
            return False
        prompt_lower = prompt.lower()
        return any(kw.lower() in prompt_lower for kw in keywords)

    def _is_peak_hour(self) -> bool:
        """Check if current time is in MiniMax peak congestion hours (14:00-18:00 HKT)."""
        import datetime
        tz_cfg = self.config.get("time_of_day", {})
        tz_name = tz_cfg.get("timezone", "Asia/Hong_Kong")
        peak = tz_cfg.get("peak_hours", {})
        start_h = peak.get("start", 14)
        end_h = peak.get("end", 18)

        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo(tz_name))
        except Exception:
            # Fallback: assume system time is HKT
            now = datetime.datetime.now()

        return start_h <= now.hour < end_h

    def _decide_delegation(
        self,
        complexity: ComplexityResult,
        budget: BudgetStatus,
        estimated_tokens: int,
        no_delegate: bool,
        prompt: str,
    ) -> tuple[bool, Optional[str]]:
        """Decide whether to use delegate_task."""
        if no_delegate:
            return False, None

        # Budget critical → no delegate (subagents multiply cost)
        if budget.is_critical:
            return False, None

        score = complexity.score
        delegate_threshold = self.complexity_cfg.get("delegate_threshold", 3.0)
        force_delegate = self.complexity_cfg.get("force_delegate", 6.0)

        # Force delegate for high complexity
        if score >= force_delegate:
            return True, "single"

        # Consider delegate for medium complexity
        if score >= delegate_threshold:
            # Check if parallel keywords present
            has_parallel_keywords = any(
                kw in prompt.lower()
                for kw in [
                    "parallel", "concurrent", "simultaneously", "at the same time",
                    "both", "all of these", "each of", "split into",
                    "split into", "break into", "multiple parts",
                ]
            )
            # Check explicit multi-step markers
            has_steps = any(
                kw in prompt.lower()
                for kw in [
                    "step 1", "step 2", "first", "second", "third",
                    "phase", "stage", "module", "component",
                    "步驟1", "步驟2", "第一", "第二", "第三",
                ]
            )

            if has_parallel_keywords:
                return True, "parallel"
            elif has_steps or score >= 4.0:
                # Score >= 4.0 → auto delegate (single) even without explicit step markers
                return True, "single"
            else:
                return True, "single"

        # Token threshold override
        if estimated_tokens > 8000:
            return True, "single"

        return False, None

    def _estimate_tokens(self, prompt: str) -> int:
        """Rough token estimation."""
        chars_per_token = self.token_cfg.get("chars_per_token", 3.5)
        margin = self.token_cfg.get("margin_multiplier", 1.2)
        base = len(prompt) / chars_per_token
        return int(base * margin)

    def get_system_prompt_addon(self) -> str:
        """
        Generate a dynamic system prompt snippet showing current budget status.
        This can be injected into the agent's system prompt at session start.

        If routing.enabled=false (auto routing disabled), outputs monitoring-only mode.
        """
        # Check if auto routing is disabled
        if not self.config.get("routing", {}).get("enabled", True):
            return self._get_monitoring_only_addon()

        budget = self.metrics.get_budget_status()
        model_usage = self.metrics.get_model_usage_today()

        lines = [
            "",
            "## ☕ Current Budget Status",
            f"- Today cost: ${budget.today_cost:.2f} / ${budget.budget_limit:.2f} ({budget.percent_used:.0f}%)",
            f"- Status: {budget.status.upper()}",
            f"- Remaining: ${budget.budget_remaining:.2f}",
            "",
            "## 📊 Today's Model Usage",
        ]
        for mu in model_usage[:5]:
            lines.append(
                f"- {mu.model}: {mu.requests} req, {mu.total_tokens:,} tokens, ${mu.cost_usd:.2f}"
            )

        lines.extend([
            "",
            "## 📝 Notes",
            "- Auto routing DISABLED (2026-04-23) — all routing is manual",
            "- Cost thresholds removed — no forced MiniMax or warnings",
            "- Use this data for reference only",
            "",
        ])

        return "\n".join(lines)

    def _get_monitoring_only_addon(self) -> str:
        """
        Generate budget status WITHOUT routing rules or enforcement.
        Used when routing.enabled=false (auto routing disabled).
        """
        budget = self.metrics.get_budget_status()
        model_usage = self.metrics.get_model_usage_today()

        lines = [
            "",
            "## ☕ Current Budget Status",
            f"- Today cost: ${budget.today_cost:.2f} / ${budget.budget_limit:.2f} ({budget.percent_used:.0f}%)",
            "- Status: MONITORING (no enforcement)",
            "- Routing: AUTO-ROUTING DISABLED — you control all model selection",
            "⚠️ No CRITICAL warnings or forced model switches",
            "",
            "## 📊 Today's Model Usage",
        ]
        for mu in model_usage[:5]:
            lines.append(
                f"- {mu.model}: {mu.requests} req, {mu.total_tokens:,} tokens, ${mu.cost_usd:.2f}"
            )

        lines.extend([
            "",
            "## 📝 Notes",
            "- Auto routing DISABLED (2026-04-23) — all routing is manual",
            "- Cost thresholds removed — no forced MiniMax or warnings",
            "- Use this data for reference only",
            "",
        ])

        return "\n".join(lines)

# ─────────────────────────────────────────────────────────────
# CLI / Testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    router = DecisionRouter()

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Implement a Redis caching layer with automatic expiration and circuit breaker pattern"

    print(f"\n{'='*60}")
    print(f"Input: {prompt[:60]}...")
    print(f"{'='*60}")

    decision = router.decide(prompt)
    print(f"\nModel:        {decision.model}")
    print(f"Provider:     {decision.provider}")
    print(f"Delegate:     {decision.should_delegate} ({decision.delegate_mode or 'N/A'})")
    print(f"Est. Cost:    ${decision.estimated_cost_usd:.4f}")
    print(f"Est. Tokens:  {decision.estimated_tokens:,}")
    print(f"Complexity:   {decision.complexity.score:.1f}/10")
    print(f"Budget:       {decision.budget.status} (${decision.budget.today_cost:.2f} today)")
    print(f"\nReasoning:")
    for r in decision.reasoning:
        print(f"  • {r}")

    print(f"\n{'='*60}")
    print("System Prompt Addon:")
    print(f"{'='*60}")
    print(router.get_system_prompt_addon())
