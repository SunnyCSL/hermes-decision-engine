#!/usr/bin/env python3
"""
MiniMax Peak Hour Auto-Detection Monitor

Runs every 30 minutes during 14:00-18:00 HKT.
Sends a minimal request to MiniMax API, measures response time.
If latency is consistently low, marks peak hours as resolved.

Usage:
    python3 minimax_peak_monitor.py           # Run single test
    python3 minimax_peak_monitor.py --summary  # Show last 7 days stats
"""

import argparse
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────
PEAK_START = 14          # 14:00 HKT
PEAK_END = 18            # 18:00 HKT
SLOW_THRESHOLD_MS = 3000  # > 3s = still peak
FAST_THRESHOLD_MS = 1500  # < 1.5s = peak likely over
CONSECUTIVE_FAST_TO_CLEAR = 3  # Need 3 fast readings to clear peak
MAX_RETRIES = 2
TEST_PROMPT = "Hi"       # Minimal prompt for speed test

STATUS_FILE = Path(__file__).parent.parent / "data" / "minimax_peak_status.json"
LOG_FILE = Path(__file__).parent.parent / "data" / "minimax_peak_log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── MiniMax API Test ────────────────────────────────────────────

def test_minimax_latency() -> dict:
    """Send a minimal request to MiniMax, measure latency."""
    import requests

    # Try env first, then read .env file
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("MINIMAX_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "MINIMAX_API_KEY not set",
            "latency_ms": -1,
            "success": False,
            "status_code": None,
        }

    # MiniMax international endpoint
    url = "https://api.minimaxi.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "MiniMax-M2.7",
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "max_tokens": 10,
        "temperature": 0.1,
    }

    start = time.perf_counter()
    error = None
    status_code = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            status_code = resp.status_code
            if resp.status_code == 200:
                break
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            break

    latency_ms = int((time.perf_counter() - start) * 1000)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "status_code": status_code,
        "error": error,
        "success": error is None and status_code == 200,
    }


# ── Status Management ───────────────────────────────────────────

def load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except Exception:
            pass
    return {
        "peak_active": True,
        "consecutive_fast": 0,
        "last_check": None,
        "peak_cleared_at": None,
        "historical_avg_ms": None,
    }


def save_status(status: dict):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2))


def append_log(result: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")


# ── Decision Logic ──────────────────────────────────────────────

def evaluate_peak_status(result: dict, current_status: dict) -> dict:
    """Decide if peak hours are still active based on latency."""
    status = dict(current_status)
    status["last_check"] = result["timestamp"]

    if not result["success"]:
        # API failed = treat as peak still active (conservative)
        status["consecutive_fast"] = 0
        status["peak_active"] = True
        status["last_failure"] = result.get("error", "unknown")
        return status

    latency = result["latency_ms"]

    if latency <= FAST_THRESHOLD_MS:
        # Fast response
        status["consecutive_fast"] = status.get("consecutive_fast", 0) + 1
        status.pop("last_failure", None)

        if status["consecutive_fast"] >= CONSECUTIVE_FAST_TO_CLEAR:
            if status.get("peak_active", True):
                status["peak_active"] = False
                status["peak_cleared_at"] = result["timestamp"]
                logger.info(
                    f"🎉 PEAK CLEARED! Latency {latency}ms for "
                    f"{CONSECUTIVE_FAST_TO_CLEAR} consecutive checks."
                )
    else:
        # Slow response - reset counter
        status["consecutive_fast"] = 0
        if not status.get("peak_active", True):
            # Was cleared but now slow again - reactivate
            status["peak_active"] = True
            status["peak_cleared_at"] = None
            logger.warning(f"🐌 Peak REACTIVATED. Latency {latency}ms > threshold.")

    return status


# ── Auto-Adjust Rules ───────────────────────────────────────────

def maybe_adjust_rules(status: dict) -> str:
    """If peak is cleared for the day, optionally notify or adjust."""
    rules_path = Path(__file__).parent.parent / "config" / "rules.yaml"

    if not status.get("peak_active", True) and status.get("peak_cleared_at"):
        # Peak was just cleared
        return (
            f"Peak hours appear to be over (cleared at {status['peak_cleared_at']}).\n"
            "MiniMax latency is back to normal.\n"
            f"You can update rules.yaml to remove peak_model_mapping if this persists."
        )
    return ""


def auto_adjust_rules(status: dict) -> str:
    """
    Generate recommendation report when peak hours appear resolved.
    Does NOT auto-modify rules.yaml — human approval required.
    """
    CONSECUTIVE_DAYS = 3
    rules_path = Path(__file__).parent.parent / "config" / "rules.yaml"

    if status.get("recommendation_generated_at"):
        return ""

    if not LOG_FILE.exists():
        return ""

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (CONSECUTIVE_DAYS * 86400)

    peak_entries = []
    with open(LOG_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if ts.timestamp() < cutoff:
                    continue
                hkt_hour = (ts.hour + 8) % 24
                if 14 <= hkt_hour < 18:
                    peak_entries.append(entry)
            except Exception:
                continue

    min_readings = CONSECUTIVE_DAYS * 4
    if len(peak_entries) < min_readings:
        return ""

    for e in peak_entries:
        if not e["success"]:
            return ""
        if e["latency_ms"] >= FAST_THRESHOLD_MS:
            return ""

    # ✅ Criteria met — generate recommendation only
    recommendation = (
        f"Peak hours appear resolved. All {len(peak_entries)} peak-hour tests "
        f"over {CONSECUTIVE_DAYS} days were fast (<{FAST_THRESHOLD_MS}ms).\n"
        "Consider updating rules.yaml peak_model_mapping:\n"
        '  trivial: "minimax-m2.7"\n'
        '  low:     "minimax-m2.7"\n'
        "(Run: hermes skill_view decision-engine → follow recommendation)"
    )

    status["recommendation_generated_at"] = now.isoformat()
    status["recommendation"] = recommendation
    save_status(status)

    logger.info(f"📋 Recommendation generated: peak hours likely resolved.")
    return recommendation

# ── Summary Report ──────────────────────────────────────────────

def show_summary(days: int = 7):
    if not LOG_FILE.exists():
        print("No log data yet.")
        return

    entries = []
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

    with open(LOG_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if ts.timestamp() > cutoff:
                    entries.append(entry)
            except Exception:
                continue

    if not entries:
        print(f"No data in last {days} days.")
        return

    success_entries = [e for e in entries if e["success"]]
    fail_entries = [e for e in entries if not e["success"]]

    print(f"=== MiniMax Peak Monitor Summary (last {days} days) ===\n")
    print(f"Total checks: {len(entries)}")
    print(f"Successful:   {len(success_entries)}")
    print(f"Failed:       {len(fail_entries)}")

    if success_entries:
        latencies = [e["latency_ms"] for e in success_entries]
        print(f"\nLatency stats:")
        print(f"  Min:    {min(latencies)} ms")
        print(f"  Max:    {max(latencies)} ms")
        print(f"  Mean:   {statistics.mean(latencies):.0f} ms")
        print(f"  Median: {statistics.median(latencies):.0f} ms")

        # Peak hour analysis (14:00-18:00 HKT)
        peak_entries = []
        for e in success_entries:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            hkt_hour = (ts.hour + 8) % 24  # Rough HKT conversion
            if 14 <= hkt_hour < 18:
                peak_entries.append(e)

        if peak_entries:
            peak_lat = [e["latency_ms"] for e in peak_entries]
            print(f"\nPeak hours (14:00-18:00 HKT) - {len(peak_entries)} checks:")
            print(f"  Mean latency: {statistics.mean(peak_lat):.0f} ms")
            slow = len([l for l in peak_lat if l > SLOW_THRESHOLD_MS])
            print(f"  Slow (>3s):   {slow}/{len(peak_entries)}")

    # Current status
    status = load_status()
    print(f"\nCurrent status: {'PEAK ACTIVE' if status.get('peak_active') else 'PEAK CLEARED'}")
    if status.get("consecutive_fast"):
        print(f"Consecutive fast checks: {status['consecutive_fast']}")


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MiniMax Peak Hour Monitor")
    parser.add_argument("--summary", action="store_true", help="Show summary report")
    parser.add_argument("--days", type=int, default=7, help="Days for summary")
    args = parser.parse_args()

    if args.summary:
        show_summary(args.days)
        return

    # Single test run
    logger.info("Testing MiniMax latency...")
    result = test_minimax_latency()
    append_log(result)

    status = load_status()
    new_status = evaluate_peak_status(result, status)
    save_status(new_status)

    if result["success"]:
        logger.info(
            f"Latency: {result['latency_ms']}ms | "
            f"Peak: {'ACTIVE' if new_status.get('peak_active') else 'CLEARED'} | "
            f"Fast streak: {new_status.get('consecutive_fast', 0)}"
        )
    else:
        logger.warning(f"Test FAILED: {result.get('error', 'unknown')}")

    msg = maybe_adjust_rules(new_status)
    if msg:
        logger.info(msg)
        # Also write to a notification file that cron can pick up
        notify_file = Path.home() / ".hermes" / "data" / "minimax_peak_notification.txt"
        notify_file.write_text(msg)

    # Auto-adjust rules.yaml if peak is confirmed resolved for multiple days
    adjust_msg = auto_adjust_rules(new_status)
    if adjust_msg:
        logger.info(adjust_msg)
        # Write recommendation to file for human review
        rec_file = Path.home() / ".hermes" / "data" / "minimax_peak_recommendation.txt"
        rec_file.write_text(adjust_msg)


if __name__ == "__main__":
    main()
