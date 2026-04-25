"""
Hermes Decision Engine — Complexity Scorer

Analyzes prompt complexity on a 0-10 scale using heuristics:
- Length & structure
- Keyword detection (coding, reasoning, multi-step)
- Pattern matching (code blocks, lists, math)
- Context hints (task type, domain)

Outputs ComplexityResult → DecisionRouter uses this + budget → model choice.
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import yaml


class ComplexityLevel(Enum):
    """Complexity levels matching 0-10 scale."""
    TRIVIAL = 0      # 0-1
    LOW = 1          # 1-3
    MEDIUM = 2       # 3-5
    HIGH = 3         # 5-7
    VERY_HIGH = 4    # 7-9
    EXTREME = 5      # 9-10

    @classmethod
    def from_score(cls, score: float) -> "ComplexityLevel":
        if score < 1:
            return cls.TRIVIAL
        elif score < 3:
            return cls.LOW
        elif score < 5:
            return cls.MEDIUM
        elif score < 7:
            return cls.HIGH
        elif score < 9:
            return cls.VERY_HIGH
        else:
            return cls.EXTREME


@dataclass
class ComplexityResult:
    score: float                      # 0-10
    level: ComplexityLevel
    factors: Dict[str, float] = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.name,
            "factors": self.factors,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }


@dataclass
class TaskContext:
    task_type: Optional[str] = None      # 'code', 'analysis', 'creative', 'trading'
    domain: Optional[str] = None         # 'legal', 'technical', 'financial'
    expected_length: Optional[int] = None
    priority: Optional[str] = None       # 'urgent', 'normal'
    user_expertise: Optional[str] = None


class ComplexityScorer:
    """
    Hybrid complexity scorer for Hermes routing decisions.

    Two-layer approach:
    1. Layer 1 (rule-based, FREE): Fast-path for obvious simple/complex prompts
    2. Layer 2 (heuristic): Full analysis for boundary cases

    Optimized for Chinese/English mixed prompts (Sunny's primary language).
    """

    # Keywords that bump complexity
    COMPLEXITY_KEYWORDS = {
        "advanced_concepts": [
            "quantum", "neural", "algorithm", "recursive", "optimization",
            "distributed", "concurrent", "asynchronous", "parallel",
            "heuristic", "stochastic", "synthesis", "paradigm",
            # Chinese equivalents
            "量子", "神經網絡", "遞迴", "佈式", "併發",
            "異步", "優化", "啟發式", "隨機",
        ],
        "analysis_terms": [
            "analyze", "evaluate", "compare", "contrast", "assess",
            "hypothesize", "correlate", "causation", "implications",
            "methodology", "framework", "trade-off", "benchmark",
            # Chinese
            "分析", "評估", "比較", "對比", "假設",
            "影響", "框架", "權衡", "基準測試",
        ],
        "multi_step_markers": [
            "first", "then", "next", "finally", "step", "stage",
            "phase", "sequence", "process", "workflow", "pipeline",
            # Chinese
            "第一", "第二", "第三", "步驟", "階段",
            "流程", "序列", "先", "然後", "接著",
            "最後", "分成", "多個", "各個",
        ],
        "code_markers": [
            "function", "class", "def ", "import ", "async ", "await ",
            "return", "variable", "loop", "debug", "compile", "deploy",
            "api", "endpoint", "database", "cache", "middleware",
            # Chinese
            "函數", "類別", "輸入", "迴圈", "調試",
            "介面", "資料庫", "快取", "中間件",
        ],
        "math_markers": [
            "equation", "formula", "calculate", "derivative", "integral",
            "matrix", "vector", "theorem", "proof", "solve for",
            # Chinese
            "方程式", "公式", "計算", "導數", "積分",
            "矩陣", "向量", "定理", "證明",
        ],
        "creative_markers": [
            "creative", "design", "invent", "compose", "brainstorm",
            "story", "narrative", "artistic", "innovative",
            # Chinese
            "創意", "設計", "發明", "撰寫", "腦力激盪",
            "故事", "藝術", "創新",
        ],
        "trading_markers": [
            "trading", "stock", "portfolio", "risk", "margin",
            "option", "derivative", "hedge", "strategy", "p&l",
            # Chinese
            "交易", "股票", "組合", "風險", "信貸",
            "期權", "次級债", "對沖", "策略", "盈虧",
        ],
        "sensitive_markers": [
            "legal", "medical", "financial", "confidential", "regulated",
            "compliance", "ethics", "gdpr", "hipaa",
            # Chinese
            "法律", "醫療", "金融", "保密", "合規",
            "倫理", "個資",
        ],
    }

    DEFAULT_WEIGHTS = {
        "length": 0.15,
        "structure": 0.15,
        "vocabulary": 0.30,
        "patterns": 0.25,
        "context": 0.15,
    }

    def __init__(self, config_path: Optional[Path] = None, weights: Optional[Dict[str, float]] = None):
        self.config_path = config_path or (
            Path(__file__).parent / "rules.yaml"
        )
        self._config = self._load_config()
        self.weights = weights or self._load_weights()

        self._sentence_re = re.compile(r"[.!?。!！?？]+")
        self._word_re = re.compile(r"[\w\u4e00-\u9fff]+")
        self._code_block_re = re.compile(r"```[\s\S]*?```|`[^`]+`")
        self._list_re = re.compile(r"^\s*[-*+\-•]\s+|^\s*\d+[.\uff0e]\s+", re.MULTILINE)

    def _load_config(self) -> Dict[str, Any]:
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _load_weights(self) -> Dict[str, float]:
        cfg = self._config.get("complexity", {})
        if "weights" in cfg:
            w = cfg["weights"]
            total = sum(w.values())
            if total > 0:
                return {k: v / total for k, v in w.items()}
        return self.DEFAULT_WEIGHTS.copy()

    def score(self, prompt: str, context: Optional[TaskContext] = None) -> ComplexityResult:
        if not prompt or not prompt.strip():
            return ComplexityResult(
                score=0.0, level=ComplexityLevel.TRIVIAL,
                factors={"empty": 0.0},
                reasoning=["Empty prompt"], confidence=1.0
            )

        factors = {
            "length": self._score_length(prompt),
            "structure": self._score_structure(prompt),
            "vocabulary": self._score_vocabulary(prompt),
            "patterns": self._score_patterns(prompt),
            "context": self._score_context(context) if context else 0.0,
        }

        weighted = sum(factors[f] * self.weights[f] for f in self.weights)
        # Scale: weighted avg of 0-5 factors → 0-10 with better discrimination
        final = max(0.0, min(10.0, weighted * 2.2 + 0.5))

        signal = sum(factors.values()) / len(factors)
        confidence = min(1.0, signal / 5.0 + 0.3)

        reasoning = [f"{k}: {v:.1f}/5" for k, v in factors.items()]
        level = ComplexityLevel.from_score(final)
        reasoning.append(f"Final: {level.name} ({final:.1f}/10)")

        return ComplexityResult(
            score=round(final, 2),
            level=level,
            factors={k: round(v, 3) for k, v in factors.items()},
            reasoning=reasoning,
            confidence=round(confidence, 3),
        )

    def _score_length(self, text: str) -> float:
        words = len(self._word_re.findall(text))
        sentences = max(1, len(self._sentence_re.findall(text)))
        chars = len(text)

        word_score = min(5.0, words / 80)
        avg_words = words / sentences
        sentence_score = min(5.0, avg_words / 12)

        if chars > 8000:
            word_score = min(5.0, word_score + 1.5)
        elif chars > 3000:
            word_score = min(5.0, word_score + 0.5)

        return (word_score + sentence_score) / 2

    def _score_structure(self, text: str) -> float:
        score = 0.0
        code_blocks = len(self._code_block_re.findall(text))
        score += min(2.5, code_blocks * 0.5)

        list_items = len(self._list_re.findall(text))
        score += min(1.5, list_items * 0.2)

        questions = text.count("?") + text.count("？")
        score += min(0.5, questions * 0.1)

        return min(5.0, score)

    def _score_vocabulary(self, text: str) -> float:
        text_lower = text.lower()
        words = set(self._word_re.findall(text_lower))

        scores = []
        for category, keywords in self.COMPLEXITY_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > 0:
                # More generous scoring for keyword matches
                scores.append(min(5.0, 1.0 + matches * 0.8))

        if not scores:
            return 0.5  # No keywords = basic

        base = sum(scores) / len(scores)
        sensitive = sum(1 for kw in self.COMPLEXITY_KEYWORDS["sensitive_markers"] if kw in text_lower)
        if sensitive > 0:
            base += min(1.5, sensitive * 0.5)

        return min(5.0, base)

    def _score_patterns(self, text: str) -> float:
        score = 0.0
        patterns = [
            (r"def\s+\w+\s*\(", 0.5),
            (r"class\s+\w+", 0.5),
            (r"import\s+\w+", 0.4),
            (r"if\s*[\(\:]|if\s+\w", 0.4),
            (r"for\s+\w+\s+in", 0.4),
            (r"while\s+|for\s+", 0.4),
            (r"=>|->", 0.4),
            (r"\{[\s\S]*?\"[\w]+\"\s*:", 0.4),
            (r"\d+\s*[\+\-\*/]\s*\d+", 0.35),
            (r"sqrt|log|sin|cos|tan|sum|product", 0.35),
            (r"compare\s+|contrast\s+|analyze\s+|evaluate\s+", 0.4),
            (r"first[,\s]+then|step\s+\d+|phase\s+\d+|stage\s+\d+", 0.4),
            (r"trading\s+|strategy\s+|portfolio\s+|risk\s+", 0.5),
            # Architecture / design patterns
            (r"cache|middleware|database|api|endpoint|service", 0.4),
            (r"pattern|architecture|layer|component|module", 0.4),
            (r"redis|postgres|elasticsearch|kafka|rabbitmq", 0.5),
            # Chinese multi-step markers
            (r"步驟\s*\d+|step\s*\d+|第一|第二|第三|先.*然後|接著", 0.4),
        ]
        for pat, weight in patterns:
            if re.search(pat, text, re.IGNORECASE):
                score += weight

        return min(5.0, score)

    def _score_context(self, context: TaskContext) -> float:
        if context is None:
            return 0.0

        score = 0.0
        task_scores = {
            "code_generation": 3.0, "code_review": 2.5, "analysis": 2.0,
            "trading": 2.5, "writing": 1.5, "translation": 1.0,
            "summarization": 0.5, "question_answering": 0.5,
        }
        if context.task_type:
            score += task_scores.get(context.task_type.lower(), 1.5)

        domain_scores = {
            "legal": 2.5, "medical": 2.5, "financial": 2.0,
            "technical": 1.5, "scientific": 2.0, "creative": 1.0, "general": 0.0,
        }
        if context.domain:
            score += domain_scores.get(context.domain.lower(), 0.5)

        if context.expected_length:
            if context.expected_length > 2000:
                score += 1.0
            elif context.expected_length > 500:
                score += 0.5

        if context.priority and context.priority.lower() == "urgent":
            score += 0.5

        return min(5.0, score)

    def score_batch(self, prompts: List[str], contexts: Optional[List[TaskContext]] = None) -> List[ComplexityResult]:
        if contexts and len(contexts) != len(prompts):
            raise ValueError("contexts length must match prompts")
        return [self.score(p, contexts[i] if contexts else None) for i, p in enumerate(prompts)]

    # ─────────────────────────────────────────────────────────────────
    # HYBRID SCORING (Layer 1: rule-based free, Layer 2: heuristic fallback)
    # ─────────────────────────────────────────────────────────────────

    def score_hybrid(self, prompt: str, context: Optional[TaskContext] = None) -> ComplexityResult:
        """
        Two-layer hybrid scoring:
        1. Rule-based fast path (FREE) — covers ~80% of prompts
        2. Full heuristic analysis — only for boundary cases (score 3-7)
        """
        # Layer 1: Rule-based fast path
        fast_score = self._score_rule_based(prompt)
        if fast_score is not None:
            # Fast path hit — return immediately, zero cost
            level = ComplexityLevel.from_score(fast_score)
            return ComplexityResult(
                score=fast_score,
                level=level,
                factors={"rule_based": fast_score},
                reasoning=[f"Layer 1 (rule-based): {level.name} ({fast_score:.1f}/10) — fast path"],
                confidence=0.85,
            )

        # Layer 2: Full heuristic analysis (boundary case)
        return self.score(prompt, context)

    def _score_rule_based(self, prompt: str) -> Optional[float]:
        """
        Pure rule-based scoring. Returns a score (0-10) if the prompt is
        obviously simple or complex. Returns None for boundary cases.
        """
        if not prompt:
            return 0.0

        text = prompt.strip()
        text_lower = text.lower()
        chars = len(text)

        # Load triggers from config if available
        hybrid_cfg = self._config.get("hybrid_scoring", {})
        rule_cfg = hybrid_cfg.get("rule_based", {})

        simple_triggers = rule_cfg.get("simple_triggers", [
            "係嗎", "係唔嗎", "幾時", "幾多錢",
            "check", "status", "hello", "hi ", "hey",
            "你好", "謝謝", "好", "ok", "yes", "no",
            "得", "唔得", "再見", "bye",
        ])
        complex_triggers = rule_cfg.get("complex_triggers", [
            "寫個程式", "寫code", "debug", "調試",
            "策略", "strategy", "trading plan",
            "分析下", "研究下", "寫個report",
            "generate report", "PDF", "cron job",
            "system design", "architecture",
        ])
        short_max = rule_cfg.get("short_max_chars", 80)
        long_min = rule_cfg.get("long_min_chars", 500)
        simple_score = rule_cfg.get("simple_score", 1.0)
        complex_score = rule_cfg.get("complex_score", 8.0)

        # Check simple triggers
        for trigger in simple_triggers:
            if trigger.lower() in text_lower:
                return simple_score

        # Check complex triggers
        for trigger in complex_triggers:
            if trigger.lower() in text_lower:
                return complex_score

        # Length-based heuristics
        if chars <= short_max:
            # Very short, no complex keywords → simple
            return simple_score
        if chars >= long_min:
            # Long prompt → at least medium, don't fast-path
            return None

        # Boundary case — let heuristic scorer handle it
        return None
