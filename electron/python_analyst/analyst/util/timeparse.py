"""Tolerant time parsing.

Backend time columns are TEXT (ISO-ish strings) in some tables and epoch
milliseconds in others (candle_time_utc_ms). Everything is normalized to
epoch milliseconds UTC; original values are preserved on the raw payloads.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Epoch-second values are ~1.7e9 while epoch-ms values are ~1.7e12.
_MS_THRESHOLD = 100_000_000_000

# MT5 CSV exports on the VPS use dotted dates: "2026.06.11 00:00".
_DOTTED_DATE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(.*)$")


def parse_time_to_ms(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_number(float(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return _from_number(float(text))
        except ValueError:
            pass
        return _from_datetime_text(text)
    return None


def _from_number(num: float) -> int | None:
    if num <= 0:
        return None
    if num >= _MS_THRESHOLD:
        return int(num)
    return int(num * 1000.0)


def _from_datetime_text(text: str) -> int | None:
    dotted = _DOTTED_DATE.match(text)
    if dotted:
        text = f"{dotted.group(1)}-{dotted.group(2)}-{dotted.group(3)}{dotted.group(4)}"
    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
