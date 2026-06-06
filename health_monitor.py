#!/usr/bin/env python3
"""External health monitor for the ventilation service.

Runs periodically from cron. Reads ventilation.log, evaluates each subsystem
category's fault/recovery state, and reboots the system if any category has
been broken for more than 1 hour.

Categories are discovered dynamically from log lines of the form
    [ERROR:<category>] ...
    [RECOVERY:<category>] ...
No category list is hardcoded; production code controls which categories
exist by what it logs.

Grace period: the monitor does nothing until the system has been up for at
least BROKEN_THRESHOLD_SECONDS. This gives the service time to come back
after a reboot, and uses the same constant as the broken-detection window
so the earliest the monitor can ever trigger a reboot is 1 hour after boot.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

from Clock import Clock
from Logger import Logger


BROKEN_THRESHOLD_SECONDS = 3600
LOOKBACK_SECONDS = 7200
DEFAULT_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ventilation.log"
)


def get_uptime_seconds() -> float:
    """Return system uptime in seconds by reading /proc/uptime."""
    with open("/proc/uptime", "r") as f:
        return float(f.read().split()[0])


def uptime_grace_period(uptime: float) -> bool:
    """Return True if the system has not been up long enough to be evaluated."""
    return uptime < BROKEN_THRESHOLD_SECONDS


_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>\w+)\s+\S+\s+-\s+"
    r"\[(?P<kind>ERROR|RECOVERY):(?P<category>[a-zA-Z0-9_]+)\]\s*"
    r"(?P<message>.*)$"
)


def parse_log_line(line: str):
    """Parse a single log line.

    Returns (timestamp, event_type, category) on a match, or None when the
    line has no structured event prefix and should be ignored.
    """
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None
    ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
    return ts, m.group("kind").lower(), m.group("category")


def parse_log(log_path: str, now: datetime):
    """Read the log file and return a chronologically sorted list of events
    within the lookback window. Each event is (timestamp, event_type, category).
    """
    events = []
    if not os.path.isfile(log_path):
        return events
    cutoff = now - timedelta(seconds=LOOKBACK_SECONDS)
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parsed = parse_log_line(line)
            if parsed is None:
                continue
            ts, _kind, _cat = parsed
            if ts >= cutoff:
                events.append(parsed)
    events.sort(key=lambda e: e[0])
    return events


def evaluate_health(events, now: datetime):
    """Return a list of categories that are currently broken for more than
    BROKEN_THRESHOLD_SECONDS (i.e. their most recent event is a fault, and
    no recovery has been seen since).
    """
    broken_since = {}
    for ts, event_type, category in events:
        if event_type == "error":
            broken_since.setdefault(category, ts)
        elif event_type == "recovery":
            broken_since.pop(category, None)

    broken = []
    for category, since in broken_since.items():
        if (now - since).total_seconds() > BROKEN_THRESHOLD_SECONDS:
            broken.append((category, since))
    return broken


def trigger_reboot(broken_categories, dry_run: bool):
    """Log the reboot decision and call sudo reboot (unless dry-run)."""
    cats = ", ".join(c for c, _ in broken_categories)
    Logger.fault("health_monitor", f"System unhealthy: {cats} broken for over 1h. Rebooting.")
    if dry_run:
        return
    try:
        subprocess.run(["sudo", "reboot"], check=False)
    except FileNotFoundError:
        Logger.fault("health_monitor", "sudo not found; cannot reboot")


def main():
    parser = argparse.ArgumentParser(description="Ventilation system health monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate and log, but do not actually reboot.")
    parser.add_argument("--log", default=DEFAULT_LOG_PATH,
                        help="Path to the ventilation log file.")
    args = parser.parse_args()

    try:
        uptime = get_uptime_seconds()
    except OSError as e:
        Logger.fault("health_monitor", f"Cannot read /proc/uptime: {e}")
        return 1

    if uptime_grace_period(uptime):
        return 0

    now = Clock.now()
    events = parse_log(args.log, now)
    broken = evaluate_health(events, now)

    if not broken:
        return 0

    trigger_reboot(broken, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
