"""A very small Telegram Bot API client (long polling, stdlib only).

Only the handful of methods this bot needs are implemented. The bot token is
never included in error messages or logs.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Any Telegram API or transport failure."""


class TelegramUnavailable(TelegramError):
    """Transient network / server problem."""


class TelegramConflict(TelegramError):
    """Another process is polling the same bot token."""


class TelegramClient:
    def __init__(self, token: str, timeout: float = 20.0):
        token = (token or "").strip()
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is empty.")
        self._token = token
        self._timeout = timeout

    def _url(self, method: str) -> str:
        return f"{API_ROOT}/bot{self._token}/{method}"

    def _call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        retries: int = 3,
    ) -> Any:
        data = json.dumps(params or {}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        last_error: Optional[TelegramError] = None

        for attempt in range(max(1, retries)):
            request = urllib.request.Request(
                self._url(method), data=data, headers=headers
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=timeout or self._timeout
                ) as response:
                    payload = json.loads(response.read().decode("utf-8", "replace"))
                if payload.get("ok"):
                    return payload.get("result")
                raise TelegramError(
                    payload.get("description") or "Telegram returned ok=false"
                )
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")
                except Exception:
                    pass
                description = body
                retry_after = None
                try:
                    parsed = json.loads(body)
                    description = parsed.get("description") or body
                    retry_after = (parsed.get("parameters") or {}).get("retry_after")
                except Exception:
                    pass

                if exc.code == 409:
                    raise TelegramConflict(
                        "another process is already polling this bot token"
                    ) from None
                if exc.code == 429:
                    wait = min(int(retry_after or 3), 30)
                    log.warning("Telegram rate limit hit; retrying in %ss", wait)
                    time.sleep(wait)
                    last_error = TelegramError(description or "rate limited")
                    continue
                if exc.code >= 500:
                    last_error = TelegramUnavailable(
                        description or f"HTTP {exc.code}"
                    )
                    time.sleep(2 ** attempt)
                    continue
                raise TelegramError(description or f"HTTP {exc.code}") from None
            except TelegramError:
                raise
            except Exception:
                # Never include the URL (it contains the token).
                last_error = TelegramUnavailable("network error talking to Telegram")
                time.sleep(2 ** attempt)

        raise last_error or TelegramError("Telegram request failed")

    # ------------------------------------------------------------------ API

    def get_me(self) -> Dict[str, Any]:
        result = self._call("getMe", retries=2)
        return result if isinstance(result, dict) else {}

    def get_updates(
        self, offset: Optional[int] = None, timeout: int = 25
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "edited_message", "channel_post"],
        }
        if offset is not None:
            params["offset"] = offset
        result = self._call(
            "getUpdates", params, timeout=timeout + 10, retries=1
        )
        return result if isinstance(result, list) else []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to: Optional[int] = None,
        disable_preview: bool = True,
    ) -> Optional[int]:
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        if reply_to is not None:
            params["reply_to_message_id"] = reply_to
            params["allow_sending_without_reply"] = True

        try:
            result = self._call("sendMessage", params, retries=3)
        except TelegramError as exc:
            if "parse entities" not in str(exc).lower():
                raise
            # Defensive fallback: never lose an alert because of markup.
            log.warning("HTML parse failed for chat %s; retrying as plain text", chat_id)
            from .alerts import strip_html

            params.pop("parse_mode", None)
            params["text"] = strip_html(text)
            result = self._call("sendMessage", params, retries=2)

        return result.get("message_id") if isinstance(result, dict) else None

    def set_my_commands(self, commands: Iterable[Tuple[str, str]]) -> None:
        payload = {
            "commands": [
                {"command": command, "description": description}
                for command, description in commands
            ]
        }
        self._call("setMyCommands", payload, retries=1)
