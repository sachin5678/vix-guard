"""Pure threshold logic for the two STBT filters.

The deal from the backtest:

* NIFTY STBT is never run when India VIX is **above** 22.
* SENSEX STBT is never run when India VIX is **below** 11.

Exactly at a threshold counts as allowed (the rule is "above" / "below").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Strategy(str, Enum):
    NIFTY = "NIFTY STBT"
    SENSEX = "SENSEX STBT"


@dataclass(frozen=True)
class Regime:
    """Which strategies are blocked at a given VIX reading."""

    nifty_blocked: bool
    sensex_blocked: bool

    def is_blocked(self, strategy: Strategy) -> bool:
        return self.nifty_blocked if strategy is Strategy.NIFTY else self.sensex_blocked


@dataclass(frozen=True)
class Change:
    """A threshold crossing."""

    strategy: Strategy
    blocked: bool
    threshold: float
    rule: str  # "above" for NIFTY, "below" for SENSEX


def regime_for(
    vix: float, *, nifty_max: float = 22.0, sensex_min: float = 11.0
) -> Regime:
    return Regime(
        nifty_blocked=vix > nifty_max,
        sensex_blocked=vix < sensex_min,
    )


def changes(
    previous: Optional[Regime],
    current: Regime,
    *,
    nifty_max: float = 22.0,
    sensex_min: float = 11.0,
) -> List[Change]:
    """Return the strategy state changes between two readings.

    ``previous is None`` means "first run": no alert, just establish a baseline.
    """
    if previous is None:
        return []

    result: List[Change] = []
    if previous.nifty_blocked != current.nifty_blocked:
        result.append(
            Change(Strategy.NIFTY, current.nifty_blocked, nifty_max, "above")
        )
    if previous.sensex_blocked != current.sensex_blocked:
        result.append(
            Change(Strategy.SENSEX, current.sensex_blocked, sensex_min, "below")
        )
    return result
