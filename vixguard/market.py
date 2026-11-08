"""India VIX quote fetching.

NSE's own API rejects scripted clients (Akamai 403), so the bot uses the
Yahoo Finance chart endpoint, which serves ``^INDIAVIX`` without a key.
The provider is isolated here so another source can be added later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import IST
from .net import NetworkError, get_json

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX"
YAHOO_RANGE = "5d"
YAHOO_INTERVAL = "1m"
MAX_PLAUSIBLE_VIX = 500.0
# During market hours, ignore a quote older than this. It stops the bot from
# treating yesterday's close as today's regime just after the open.
MAX_QUOTE_AGE = timedelta(hours=4)


class DataUnavailable(RuntimeError):
    """Raised when no usable India VIX quote could be fetched."""


@dataclass(frozen=True)
class Quote:
    value: float
    as_of: Optional[datetime]
    source: str

    def age(self, now: Optional[datetime] = None) -> Optional[timedelta]:
        if self.as_of is None:
            return None
        return (now or datetime.now(IST)) - self.as_of

    def is_stale(
        self,
        max_age: timedelta = timedelta(minutes=30),
        now: Optional[datetime] = None,
    ) -> bool:
        age = self.age(now)
        return age is not None and age > max_age


def parse_yahoo_payload(payload: Any) -> Quote:
    """Extract the latest India VIX print from a Yahoo chart response."""
    if not isinstance(payload, dict):
        raise DataUnavailable("Yahoo Finance returned an unexpected response.")

    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        message = error.get("description") if isinstance(error, dict) else str(error)
        raise DataUnavailable(f"Yahoo Finance error: {message}")

    results = chart.get("result") or []
    if not results:
        raise DataUnavailable("Yahoo Finance returned no data for India VIX.")

    result = results[0] or {}
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    indicator_quotes = (result.get("indicators") or {}).get("quote") or []
    closes = indicator_quotes[0].get("close") if indicator_quotes else None
    if not isinstance(closes, list):
        closes = []

    last_point = None
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            last_point = (int(timestamp), float(close))
        except (TypeError, ValueError):
            continue

    if last_point is not None:
        timestamp, value = last_point
        as_of = datetime.fromtimestamp(timestamp, IST)
    else:
        # Holiday / just-after-open: intraday bars can be empty, but meta
        # usually still carries the last price.
        raw_price = meta.get("regularMarketPrice")
        if raw_price is None:
            raw_price = meta.get("fulldayPrice")
        if raw_price is None:
            raise DataUnavailable("Yahoo Finance returned no usable India VIX price.")
        try:
            value = float(raw_price)
        except (TypeError, ValueError):
            raise DataUnavailable(
                "Yahoo Finance returned a non-numeric India VIX price."
            ) from None
        raw_time = meta.get("regularMarketTime")
        as_of = datetime.fromtimestamp(int(raw_time), IST) if raw_time else None

    if not (0 < value < MAX_PLAUSIBLE_VIX):
        raise DataUnavailable(f"Implausible India VIX value: {value!r}")

    return Quote(value=round(value, 2), as_of=as_of, source="Yahoo Finance")


def fetch_quote(timeout: float = 15.0) -> Quote:
    """Fetch the latest India VIX reading or raise :class:`DataUnavailable`."""
    try:
        payload = get_json(
            YAHOO_CHART_URL,
            params={"range": YAHOO_RANGE, "interval": YAHOO_INTERVAL},
            timeout=timeout,
        )
    except NetworkError as exc:
        raise DataUnavailable(str(exc)) from None
    return parse_yahoo_payload(payload)
