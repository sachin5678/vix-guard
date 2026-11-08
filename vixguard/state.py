"""Persistent state, so a restart does not re-send every alert.

The state file stores the last observed regime, not just the last price:
crossings are detected against "which strategies were blocked last time".
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .rules import Regime

SCHEMA_VERSION = 1


@dataclass
class State:
    vix: Optional[float] = None
    nifty_blocked: Optional[bool] = None
    sensex_blocked: Optional[bool] = None
    updated_at: Optional[str] = None
    last_digest: Optional[str] = None

    def regime(self) -> Optional[Regime]:
        if self.nifty_blocked is None or self.sensex_blocked is None:
            return None
        return Regime(
            nifty_blocked=self.nifty_blocked,
            sensex_blocked=self.sensex_blocked,
        )

    def record(self, vix: float, regime: Regime, when: datetime) -> None:
        self.vix = round(float(vix), 2)
        self.nifty_blocked = regime.nifty_blocked
        self.sensex_blocked = regime.sensex_blocked
        self.updated_at = when.isoformat()

    def save(self, path: Path) -> None:
        """Write atomically so a crash cannot leave a half-written state file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": SCHEMA_VERSION}
        payload.update(asdict(self))
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".vixguard-state-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @classmethod
    def load(cls, path: Path) -> "State":
        path = Path(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            return cls()

        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            return cls()

        vix = raw.get("vix")
        nifty = raw.get("nifty_blocked")
        sensex = raw.get("sensex_blocked")
        updated_at = raw.get("updated_at")
        last_digest = raw.get("last_digest")

        return cls(
            vix=(
                float(vix)
                if isinstance(vix, (int, float)) and not isinstance(vix, bool)
                else None
            ),
            nifty_blocked=nifty if isinstance(nifty, bool) else None,
            sensex_blocked=sensex if isinstance(sensex, bool) else None,
            updated_at=updated_at if isinstance(updated_at, str) else None,
            last_digest=last_digest if isinstance(last_digest, str) else None,
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
