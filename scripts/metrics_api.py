"""
Hermes Decision Engine — Metrics API Module

Real-time cost/token query from central_metrics.db (metrics_log table).
Provides cached, thread-safe access to actual usage data.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import yaml

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Current daily budget status."""
    today_cost: float
    today_tokens: int
    today_requests: int
    budget_limit: float
    budget_remaining: float
    percent_used: float
    status: str  # "healthy" | "warning" | "critical"
    
    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"
    
    @property
    def is_warning(self) -> bool:
        return self.status == "warning"
    
    @property
    def is_critical(self) -> bool:
        return self.status == "critical"


@dataclass
class ModelUsage:
    """Usage stats for a specific model today."""
    model: str
    provider: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    avg_duration_sec: float


class MetricsAPI:
    """
    Query real-time cost/token metrics from central_metrics.db.
    
    Schema expected (metrics_log table):
        timestamp, component, model, input_tokens, output_tokens, 
        total_tokens, duration_sec, cost_usd, status, ...
    """
    
    _lock = threading.Lock()
    _instance: Optional["MetricsAPI"] = None
    
    def __new__(cls, db_path: Optional[Path] = None, config_path: Optional[Path] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(
        self,
        db_path: Optional[Path] = None,
        config_path: Optional[Path] = None
    ):
        if self._initialized:
            return
        self._initialized = True
        
        home = Path.home()
        self.db_path = db_path or (home / ".hermes" / "data" / "central_metrics.db")
        self.config_path = config_path or (home / ".hermes" / "scripts" / "decision_engine" / "rules.yaml")
        
        self._config = self._load_config()
        self._local = threading.local()
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = self._config.get("database", {}).get("cache_ttl", 30)
        
        self.budget_limit = self._config.get("cost_budget", {}).get("daily_limit", 2.00)
        self.warning_threshold = self._config.get("cost_budget", {}).get("warning_threshold", 1.50)
        self.critical_threshold = self._config.get("cost_budget", {}).get("critical_threshold", 1.80)
        
        logger.info(f"MetricsAPI ready: db={self.db_path}")
    
    def _load_config(self) -> Dict:
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Config load failed: {e}")
        return {}
    
    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _cached(self, key: str, fn, *args, **kwargs):
        now = time.time()
        if key in self._cache:
            val, ts = self._cache[key]
            if now - ts < self._cache_ttl:
                return val
        val = fn(*args, **kwargs)
        self._cache[key] = (val, now)
        return val
    
    def get_budget_status(self) -> BudgetStatus:
        """Get today's budget status from metrics_log."""
        return self._cached("budget_status", self._query_budget_status)
    
    def _query_budget_status(self) -> BudgetStatus:
        today = datetime.now().strftime("%Y-%m-%d")
        today_start = f"{today}T00:00:00+00:00"
        today_end = f"{today}T23:59:59+00:00"
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as requests,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(cost_usd), 0) as cost
                FROM metrics_log
                WHERE timestamp >= ? AND timestamp <= ?
                  AND status != 'error'
            """, (today_start, today_end))
            
            row = cursor.fetchone()
            today_cost = float(row["cost"] or 0)
            today_tokens = int(row["total_tokens"] or 0)
            today_requests = int(row["requests"] or 0)
            
            remaining = max(0, self.budget_limit - today_cost)
            pct = (today_cost / self.budget_limit * 100) if self.budget_limit > 0 else 0
            
            if today_cost >= self.critical_threshold:
                status = "critical"
            elif today_cost >= self.warning_threshold:
                status = "warning"
            else:
                status = "healthy"
            
            return BudgetStatus(
                today_cost=round(today_cost, 4),
                today_tokens=today_tokens,
                today_requests=today_requests,
                budget_limit=self.budget_limit,
                budget_remaining=round(remaining, 4),
                percent_used=round(pct, 1),
                status=status
            )
            
        except sqlite3.Error as e:
            logger.error(f"Budget query failed: {e}")
            return BudgetStatus(
                today_cost=0, today_tokens=0, today_requests=0,
                budget_limit=self.budget_limit, budget_remaining=self.budget_limit,
                percent_used=0, status="unknown"
            )
    
    def get_model_usage_today(self) -> List[ModelUsage]:
        """Get per-model usage breakdown for today."""
        return self._cached("model_usage_today", self._query_model_usage_today)
    
    def _query_model_usage_today(self) -> List[ModelUsage]:
        today = datetime.now().strftime("%Y-%m-%d")
        today_start = f"{today}T00:00:00+00:00"
        today_end = f"{today}T23:59:59+00:00"
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    model,
                    provider,
                    COUNT(*) as requests,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(cost_usd), 0) as cost,
                    COALESCE(AVG(duration_sec), 0) as avg_duration
                FROM metrics_log
                WHERE timestamp >= ? AND timestamp <= ?
                  AND status != 'error'
                GROUP BY model, provider
                ORDER BY cost DESC
            """, (today_start, today_end))
            
            results = []
            for row in cursor.fetchall():
                results.append(ModelUsage(
                    model=row["model"] or "unknown",
                    provider=row["provider"] or "unknown",
                    requests=row["requests"],
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    total_tokens=row["total_tokens"],
                    cost_usd=round(float(row["cost"] or 0), 4),
                    avg_duration_sec=round(float(row["avg_duration"] or 0), 2)
                ))
            return results
            
        except sqlite3.Error as e:
            logger.error(f"Model usage query failed: {e}")
            return []
    
    def get_cost_last_n_days(self, n: int = 7) -> Dict[str, float]:
        """Get daily cost for last N days."""
        return self._cached(f"cost_last_{n}_days", self._query_cost_last_n_days, n)
    
    def _query_cost_last_n_days(self, n: int) -> Dict[str, float]:
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            since = (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")
            
            cursor.execute("""
                SELECT 
                    DATE(timestamp) as day,
                    COALESCE(SUM(cost_usd), 0) as cost
                FROM metrics_log
                WHERE timestamp >= ? AND status != 'error'
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
            """, (since,))
            
            return {row["day"]: round(float(row["cost"]), 4) for row in cursor.fetchall()}
            
        except sqlite3.Error as e:
            logger.error(f"History query failed: {e}")
            return {}
    
    def estimate_request_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a hypothetical request using config pricing."""
        models = self._config.get("models", {})
        cfg = models.get(model, {})
        
        in_rate = cfg.get("cost_per_1k_input", 0.001)
        out_rate = cfg.get("cost_per_1k_output", 0.003)
        
        cost = (input_tokens / 1000 * in_rate) + (output_tokens / 1000 * out_rate)
        return round(cost, 6)
    
    def get_cheapest_available_model(self) -> str:
        """Return the cheapest model key from config."""
        models = self._config.get("models", {})
        cheapest = None
        min_cost = float("inf")
        
        for key, cfg in models.items():
            cost = cfg.get("cost_per_1k_input", 0) + cfg.get("cost_per_1k_output", 0)
            if cost < min_cost:
                min_cost = cost
                cheapest = key
        
        return cheapest or "minimax-m2.7"
