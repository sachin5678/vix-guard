"""Configuration for VIX Guard.

Everything comes from environment variables, optionally loaded from a local
``.env`` file. Standard library only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

# India has no DST, so a fixed offset is exact and needs no tzdata package.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


class ConfigError(ValueError):
    """Raised when the environment configuration is invalid."""


def load_env_file(path: Path) -> None:
    """Load ``KEY=VALUE`` lines into os.environ without overriding real env vars."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be true/false, got {raw!r}")


def _env_time(name: str, default: time) -> time:
    raw = _env(name)
    if not raw:
        return default
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        raise ConfigError(f"{name} must look like HH:MM (24h), got {raw!r}") from None


def _env_path(name: str, default: Path) -> Path:
    raw = _env(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_chat_ids(raw: str) -> Tuple[int, ...]:
    ids = []
    for chunk in raw.replace(";", ",").replace(" ", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            raise ConfigError(
                f"TELEGRAM_CHAT_ID has an invalid entry {chunk!r}. "
                "Use numeric chat IDs, comma-separated."
            ) from None
    # dict preserves order and removes duplicates
    return tuple(dict.fromkeys(ids))


@dataclass(frozen=True)
class Settings:
    """Runtime settings, validated once at startup."""

    telegram_token: str = ""
    chat_ids: Tuple[int, ...] = ()
    nifty_max_vix: float = 22.0
    sensex_min_vix: float = 11.0
    poll_seconds: int = 300
    state_file: Path = PROJECT_ROOT / "state.json"
    timezone: tzinfo = IST
    market_open: time = time(9, 5)
    market_close: time = time(15, 40)
    digest_after: time = time(9, 10)
    announce_on_start: bool = True
    daily_digest: bool = True
    log_file: Optional[Path] = None

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Settings":
        if env_file is not None:
            load_env_file(Path(env_file))
        else:
            load_env_file(DEFAULT_ENV_FILE)
            cwd_env = Path.cwd() / ".env"
            if cwd_env != DEFAULT_ENV_FILE:
                load_env_file(cwd_env)

        nifty_max = _env_float("NIFTY_MAX_VIX", 22.0)
        sensex_min = _env_float("SENSEX_MIN_VIX", 11.0)
        poll_seconds = _env_int("POLL_SECONDS", 300)
        market_open = _env_time("MARKET_OPEN", time(9, 5))
        market_close = _env_time("MARKET_CLOSE", time(15, 40))

        if poll_seconds < 15:
            raise ConfigError("POLL_SECONDS must be at least 15 seconds.")
        if not (0 < sensex_min < nifty_max < 1000):
            raise ConfigError(
                "VIX thresholds must satisfy 0 < SENSEX_MIN_VIX < NIFTY_MAX_VIX < 1000 "
                f"(got {sensex_min:g} and {nifty_max:g})."
            )
        if market_open >= market_close:
            raise ConfigError("MARKET_OPEN must be before MARKET_CLOSE.")

        log_file: Optional[Path] = None
        if _env("LOG_FILE"):
            path = Path(_env("LOG_FILE")).expanduser()
            log_file = path if path.is_absolute() else PROJECT_ROOT / path

        return cls(
            telegram_token=_env("TELEGRAM_BOT_TOKEN"),
            chat_ids=_parse_chat_ids(_env("TELEGRAM_CHAT_ID")),
            nifty_max_vix=nifty_max,
            sensex_min_vix=sensex_min,
            poll_seconds=poll_seconds,
            state_file=_env_path("STATE_FILE", PROJECT_ROOT / "state.json"),
            market_open=market_open,
            market_close=market_close,
            digest_after=_env_time("DIGEST_AFTER", time(9, 10)),
            announce_on_start=_env_bool("ANNOUNCE_ON_START", True),
            daily_digest=_env_bool("DAILY_DIGEST", True),
            log_file=log_file,
        )

    def require_telegram(self) -> None:
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_ids:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise ConfigError(
                "Missing " + " and ".join(missing) + ". "
                "Copy .env.example to .env, fill it in, and try again."
            )

    def is_market_time(self, when: datetime) -> bool:
        """True on weekdays inside the configured market window."""
        return when.weekday() < 5 and self.market_open <= when.time() <= self.market_close

    def summary(self) -> str:
        token = "set" if self.telegram_token else "missing"
        return (
            f"NIFTY off above {self.nifty_max_vix:g}, SENSEX off below "
            f"{self.sensex_min_vix:g}; {len(self.chat_ids)} chat(s); "
            f"token {token}; poll {self.poll_seconds}s; state {self.state_file}"
        )
