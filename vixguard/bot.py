"""The long-running bot: polling loop, scheduled checks and commands."""

from __future__ import annotations

import html
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from . import alerts, market, rules
from .config import Settings
from .state import State
from .telegram import TelegramClient, TelegramConflict, TelegramError

log = logging.getLogger(__name__)

COMMANDS = [
    ("status", "Current VIX + both strategy states"),
    ("vix", "Just the current India VIX"),
    ("rules", "Your STBT thresholds"),
    ("id", "Show this chat's ID"),
    ("help", "How this bot works"),
]


def help_text(settings: Settings) -> str:
    return "\n".join(
        [
            "<b>VIX Guard</b>",
            "Watches India VIX and pings you when your STBT filters flip.",
            "",
            "<b>Rules</b>",
            f"• NIFTY STBT — off when VIX is above {settings.nifty_max_vix:g}",
            f"• SENSEX STBT — off when VIX is below {settings.sensex_min_vix:g}",
            "",
            "<b>Commands</b>",
            "/status — current VIX + both states",
            "/vix — just the number",
            "/rules — thresholds",
            "/id — this chat's ID",
            "/help — this message",
            "",
            (
                "Alerts arrive automatically during market hours "
                "(09:05–15:40 IST, Mon–Fri)."
            ),
        ]
    )


def rules_text(settings: Settings) -> str:
    return "\n".join(
        [
            "<b>Your STBT rules</b>",
            "",
            (
                "• NIFTY STBT — <b>OFF</b> when VIX is above "
                f"{settings.nifty_max_vix:g}"
            ),
            (
                "• SENSEX STBT — <b>OFF</b> when VIX is below "
                f"{settings.sensex_min_vix:g}"
            ),
            (
                "• Both are ON when VIX is between "
                f"{settings.sensex_min_vix:g} and {settings.nifty_max_vix:g}"
            ),
            "",
            (
                "Change thresholds with NIFTY_MAX_VIX and SENSEX_MIN_VIX "
                "in .env, then restart the bot."
            ),
        ]
    )


class VixGuardBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = TelegramClient(settings.telegram_token)
        self.state = State.load(settings.state_file)
        self.offset: Optional[int] = None
        self.next_check = 0.0
        self.consecutive_failures = 0
        self.feed_down = False
        self.last_good: Optional[datetime] = None

    # ------------------------------------------------------------- lifecycle

    def run(self) -> None:
        me = self.client.get_me()
        username = me.get("username") or "unknown"
        log.info("Connected to Telegram as @%s", username)

        try:
            self.client.set_my_commands(COMMANDS)
        except TelegramError as exc:
            log.warning("Could not register the command menu: %s", exc)

        self.discard_pending_updates()
        if self.settings.announce_on_start:
            self.announce_start()

        log.info("Watching India VIX: %s", self.settings.summary())
        self.next_check = 0.0
        conflicts = 0

        while True:
            if time.monotonic() >= self.next_check:
                try:
                    self.run_check()
                except Exception:
                    log.exception("VIX check failed unexpectedly")
                self.next_check = time.monotonic() + self.settings.poll_seconds

            try:
                updates = self.client.get_updates(offset=self.offset, timeout=25)
                conflicts = 0
            except TelegramConflict as exc:
                conflicts += 1
                if conflicts >= 2:
                    raise SystemExit(f"Telegram conflict: {exc}") from None
                log.warning("%s — retrying in 3s", exc)
                time.sleep(3)
                continue
            except TelegramError as exc:
                log.warning("Telegram polling failed: %s", exc)
                time.sleep(5)
                continue

            for update in updates:
                try:
                    self.offset = int(update["update_id"]) + 1
                except (KeyError, TypeError, ValueError):
                    continue
                try:
                    self.handle_update(update)
                except Exception:
                    log.exception("Could not handle a Telegram update")

    def discard_pending_updates(self) -> None:
        """Drop commands that arrived while the bot was offline."""
        try:
            pending = self.client.get_updates(timeout=0)
        except TelegramConflict:
            raise
        except TelegramError as exc:
            log.warning("Could not flush old updates: %s", exc)
            return
        for update in pending:
            try:
                self.offset = int(update["update_id"]) + 1
            except (KeyError, TypeError, ValueError):
                pass
        if pending:
            log.info("Discarded %d old update(s)", len(pending))

    # ---------------------------------------------------------------- checks

    def run_check(self, force: bool = False) -> None:
        now = datetime.now(self.settings.timezone)
        if not force and not self.settings.is_market_time(now):
            return

        try:
            quote = market.fetch_quote()
        except market.DataUnavailable as exc:
            self.consecutive_failures += 1
            log.warning(
                "India VIX fetch failed (%d in a row): %s",
                self.consecutive_failures,
                exc,
            )
            if self.consecutive_failures >= 3 and not self.feed_down:
                self.feed_down = True
                self.broadcast(alerts.render_feed_down(self.last_good))
            return

        self.consecutive_failures = 0
        self.last_good = now
        if not force and quote.is_stale(market.MAX_QUOTE_AGE, now):
            log.info(
                "Ignoring stale quote from %s; waiting for the next print",
                quote.as_of,
            )
            return
        if self.feed_down:
            self.feed_down = False
            self.broadcast(alerts.render_feed_up(quote))

        self.process_quote(quote, now)

    def process_quote(self, quote: market.Quote, now: datetime) -> None:
        regime = self._regime(quote)
        events = rules.changes(
            self.state.regime(),
            regime,
            nifty_max=self.settings.nifty_max_vix,
            sensex_min=self.settings.sensex_min_vix,
        )

        delivered = 0
        for change in events:
            log.info(
                "Threshold event: %s -> %s",
                change.strategy.value,
                "BLOCKED" if change.blocked else "ALLOWED",
            )
            delivered += self.broadcast(
                alerts.render_change(change, quote, regime, self.settings)
            )

        # If Telegram is unreachable, keep the old regime so the next check
        # retries the alert instead of silently losing it.
        if events and delivered == 0:
            log.error(
                "No threshold alert could be delivered; will retry on the next check"
            )
            return

        if self._digest_due(now, quote, sent_change=bool(events)):
            if self.broadcast(
                alerts.render_digest(quote, regime, now, self.settings)
            ):
                self.state.last_digest = now.date().isoformat()

        self.state.record(quote.value, regime, now)
        self._save_state()

    def _digest_due(
        self, now: datetime, quote: market.Quote, *, sent_change: bool
    ) -> bool:
        if not self.settings.daily_digest or sent_change:
            return False
        if now.time() < self.settings.digest_after:
            return False
        if self.state.last_digest == now.date().isoformat():
            return False
        # Do not send yesterday's close as today's plan (holidays / pre-open).
        if quote.as_of is not None and quote.as_of.date() != now.date():
            return False
        return True

    def _regime(self, quote: market.Quote) -> rules.Regime:
        return rules.regime_for(
            quote.value,
            nifty_max=self.settings.nifty_max_vix,
            sensex_min=self.settings.sensex_min_vix,
        )

    def _save_state(self) -> None:
        try:
            self.state.save(self.settings.state_file)
        except OSError as exc:
            log.error("Could not save state to %s: %s", self.settings.state_file, exc)

    def announce_start(self) -> None:
        now = datetime.now(self.settings.timezone)
        try:
            quote = market.fetch_quote()
        except market.DataUnavailable as exc:
            log.warning("Startup quote unavailable: %s", exc)
            self.broadcast(alerts.render_online_without_quote())
            return

        regime = self._regime(quote)
        for change in rules.changes(
            self.state.regime(),
            regime,
            nifty_max=self.settings.nifty_max_vix,
            sensex_min=self.settings.sensex_min_vix,
        ):
            self.broadcast(alerts.render_change(change, quote, regime, self.settings))

        self.broadcast(alerts.render_snapshot(quote, regime, self.settings))
        # The snapshot already carries today's plan, so do not follow it with
        # an identical digest on the first regular check.
        if self._digest_due(now, quote, sent_change=False):
            self.state.last_digest = now.date().isoformat()
        self.state.record(quote.value, regime, now)
        self._save_state()

    # -------------------------------------------------------------- commands

    def handle_update(self, update: Dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return

        command = text.split()[0][1:].split("@", 1)[0].lower()
        message_id = message.get("message_id")

        if command in ("start", "help"):
            self.reply(chat_id, help_text(self.settings), message_id)
            return
        if command == "id":
            name = (
                chat.get("title")
                or " ".join(
                    part
                    for part in (chat.get("first_name"), chat.get("last_name"))
                    if part
                )
                or chat.get("username")
                or ""
            )
            reply = f"<b>Chat ID</b>\n<code>{chat_id}</code>"
            if name:
                reply += f"\n{html.escape(str(name))}"
            self.reply(chat_id, reply, message_id)
            return
        if command == "ping":
            stamp = datetime.now(self.settings.timezone).strftime("%H:%M IST")
            self.reply(chat_id, f"pong · {stamp}", message_id)
            return

        if chat_id not in self.settings.chat_ids:
            self.reply(
                chat_id,
                "This bot is private. Add this chat ID to TELEGRAM_CHAT_ID to use it.",
                message_id,
            )
            return

        if command == "status":
            self.reply(chat_id, self._status_html(), message_id)
        elif command == "vix":
            self.reply(chat_id, self._vix_html(), message_id)
        elif command == "rules":
            self.reply(chat_id, rules_text(self.settings), message_id)
        else:
            self.reply(chat_id, "Unknown command. Try /help.", message_id)

    def _status_html(self) -> str:
        try:
            quote = market.fetch_quote()
        except market.DataUnavailable as exc:
            lines = ["<b>⚠️ India VIX unavailable</b>", html.escape(str(exc))]
            if self.state.vix is not None:
                lines += ["", f"Last saved reading: <b>{self.state.vix:.2f}</b>"]
            return "\n".join(lines)
        return alerts.render_status(quote, self._regime(quote), self.settings)

    def _vix_html(self) -> str:
        try:
            quote = market.fetch_quote()
        except market.DataUnavailable:
            return "India VIX is unavailable right now."
        return (
            f"India VIX <b>{quote.value:.2f}</b>\n"
            f"<i>{alerts.as_of_line(quote)}</i>"
        )

    # ---------------------------------------------------------------- output

    def reply(self, chat_id: int, text: str, reply_to: Optional[int] = None) -> None:
        try:
            self.client.send_message(chat_id, text, reply_to=reply_to)
        except TelegramError as exc:
            log.warning("Reply to %s failed: %s", chat_id, exc)

    def broadcast(self, text: str) -> int:
        delivered = 0
        for chat_id in self.settings.chat_ids:
            try:
                self.client.send_message(chat_id, text)
                delivered += 1
            except TelegramError as exc:
                log.warning("Alert to %s failed: %s", chat_id, exc)
        return delivered
