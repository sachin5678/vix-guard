"""Telegram message rendering.

Messages use Telegram's HTML parse mode (``<b>``, ``<i>``). The rule text is
written with words ("above", "below") so raw ``<`` / ``>`` never need escaping.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .config import IST, Settings
from .market import Quote
from .rules import Change, Regime, Strategy

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Turn a Telegram HTML message into readable plain text."""
    return _TAG_RE.sub("", text)


def as_of_line(quote: Quote) -> str:
    if quote.as_of is None:
        return f"Source: {quote.source}"
    stamp = quote.as_of.astimezone(IST).strftime("%d %b %Y, %H:%M IST")
    return f"As of {stamp} · {quote.source}"


def _both_states(regime: Regime) -> str:
    nifty = "❌ <b>OFF</b>" if regime.nifty_blocked else "✅ <b>ON</b>"
    sensex = "❌ <b>OFF</b>" if regime.sensex_blocked else "✅ <b>ON</b>"
    return f"NIFTY STBT — {nifty}\nSENSEX STBT — {sensex}"


def render_change(change: Change, quote: Quote, regime: Regime, settings: Settings) -> str:
    """The alert for one threshold crossing (stop or resume)."""
    if change.strategy is Strategy.NIFTY:
        limit = change.threshold
        if change.blocked:
            icon = "🔴"
            title = "STOP — NIFTY STBT"
            condition = f"above {limit:g}"
            rule = f"never run NIFTY STBT when VIX is above {limit:g}"
            action = "skip NIFTY STBT · no overnight NIFTY shorts"
        else:
            icon = "🟢"
            title = "BACK ON — NIFTY STBT"
            condition = f"back at or below {limit:g}"
            rule = f"NIFTY STBT needs VIX at or below {limit:g}"
            action = "normal NIFTY STBT rules apply again"
    else:
        limit = change.threshold
        if change.blocked:
            icon = "🔴"
            title = "STOP — SENSEX STBT"
            condition = f"below {limit:g}"
            rule = f"never run SENSEX STBT when VIX is below {limit:g}"
            action = "skip SENSEX STBT · no overnight SENSEX shorts"
        else:
            icon = "🟢"
            title = "BACK ON — SENSEX STBT"
            condition = f"back at or above {limit:g}"
            rule = f"SENSEX STBT needs VIX at or above {limit:g}"
            action = "normal SENSEX STBT rules apply again"

    return "\n".join(
        [
            f"<b>{icon} {title}</b>",
            "",
            f"India VIX <b>{quote.value:.2f}</b> — {condition}.",
            f"<i>{as_of_line(quote)}</i>",
            "",
            "<b>Rule</b>",
            rule,
            "",
            "<b>Do</b>",
            action,
            "",
            _both_states(regime),
        ]
    )


def render_status(
    quote: Quote,
    regime: Regime,
    settings: Settings,
    title: str = "📊 VIX Guard — status",
) -> str:
    return "\n".join(
        [
            f"<b>{title}</b>",
            "",
            f"India VIX <b>{quote.value:.2f}</b>",
            f"<i>{as_of_line(quote)}</i>",
            "",
            _both_states(regime),
            "",
            (
                "Both are ON when VIX is between "
                f"{settings.sensex_min_vix:g} and {settings.nifty_max_vix:g}."
            ),
        ]
    )


def render_snapshot(quote: Quote, regime: Regime, settings: Settings) -> str:
    return render_status(quote, regime, settings, title="🤖 VIX Guard is online")


def render_online_without_quote() -> str:
    return (
        "<b>🤖 VIX Guard is online</b>\n\n"
        "I could not fetch India VIX right now. I will keep retrying during "
        "market hours (09:05–15:40 IST, Mon–Fri)."
    )


def render_digest(
    quote: Quote, regime: Regime, now: datetime, settings: Settings
) -> str:
    stamp = now.astimezone(IST).strftime("%H:%M IST")
    return "\n".join(
        [
            f"<b>☀️ VIX plan — {now.astimezone(IST).strftime('%a %d %b')}</b>",
            "",
            f"India VIX <b>{quote.value:.2f}</b> at {stamp}",
            _both_states(regime),
            "",
            (
                "Rule: NIFTY off above "
                f"{settings.nifty_max_vix:g} · SENSEX off below "
                f"{settings.sensex_min_vix:g}."
            ),
        ]
    )


def render_feed_down(last_good: Optional[datetime]) -> str:
    if last_good is None:
        last = "never"
    else:
        last = last_good.astimezone(IST).strftime("%H:%M IST")
    return (
        "<b>⚠️ VIX feed problem</b>\n\n"
        "I could not fetch India VIX 3 times in a row. "
        f"Last good check: {last}.\n"
        "Alerts are paused until the feed recovers — check the network or "
        "the data source."
    )


def render_feed_up(quote: Quote) -> str:
    return (
        "<b>✅ VIX feed back</b>\n\n"
        f"India VIX <b>{quote.value:.2f}</b> · alerts are live again."
    )


def status_plain(quote: Quote, regime: Regime, settings: Settings) -> str:
    nifty = "OFF" if regime.nifty_blocked else "ON"
    sensex = "OFF" if regime.sensex_blocked else "ON"
    return "\n".join(
        [
            "VIX Guard — status",
            f"India VIX {quote.value:.2f}",
            as_of_line(quote),
            "",
            (
                f"NIFTY STBT  : {nifty:<3}  (off above "
                f"{settings.nifty_max_vix:g})"
            ),
            (
                f"SENSEX STBT : {sensex:<3}  (off below "
                f"{settings.sensex_min_vix:g})"
            ),
            "",
            (
                "Both ON when VIX is between "
                f"{settings.sensex_min_vix:g} and {settings.nifty_max_vix:g}."
            ),
        ]
    )
