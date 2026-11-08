"""Command line interface: run the bot, one-shot checks, status, whoami."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional

from . import alerts, market, rules
from .config import ConfigError, Settings
from .state import State
from .telegram import TelegramClient, TelegramConflict, TelegramError

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vixguard",
        description=(
            "India VIX threshold alerts for NIFTY / SENSEX STBT rules. "
            "NIFTY STBT is stopped above 22, SENSEX STBT below 11."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="load settings from this file instead of the project .env",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    sub.add_parser("run", help="run the Telegram bot (long polling)")

    check = sub.add_parser(
        "check", help="run one VIX check (for cron / Task Scheduler)"
    )
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be sent and do not save state",
    )
    check.add_argument(
        "--force", action="store_true", help="check outside market hours"
    )
    check.add_argument(
        "--no-announce",
        action="store_true",
        help="stay silent on the very first run (baseline only)",
    )
    check.add_argument("--quiet", action="store_true", help="only print errors")

    status = sub.add_parser("status", help="print the current VIX and rule state")
    status.add_argument("--json", action="store_true", help="machine-readable output")

    sub.add_parser("whoami", help="show chat IDs that recently messaged the bot")
    return parser


def _configure_logging(verbose: bool, log_file: Optional[Path]) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(
                RotatingFileHandler(
                    str(log_file),
                    maxBytes=2_000_000,
                    backupCount=3,
                    encoding="utf-8",
                )
            )
        except OSError as exc:
            print(f"Warning: cannot write log file {log_file}: {exc}", file=sys.stderr)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _cmd_run(settings: Settings) -> int:
    settings.require_telegram()
    log.info("Settings: %s", settings.summary())
    from .bot import VixGuardBot

    VixGuardBot(settings).run()
    return 0


def _cmd_check(settings: Settings, args: argparse.Namespace) -> int:
    now = datetime.now(settings.timezone)
    if not args.force and not settings.is_market_time(now):
        if not args.quiet:
            print(
                "Outside the market window (Mon–Fri 09:05–15:40 IST). "
                "Use --force to check anyway."
            )
        return 0

    quote = market.fetch_quote()
    if not args.force and quote.is_stale(market.MAX_QUOTE_AGE, now):
        if not args.quiet:
            print(
                "The latest quote is stale ("
                f"{quote.as_of:%d %b %Y, %H:%M IST}"
                "). Waiting for the next market print; use --force to use it."
            )
        return 0

    regime = rules.regime_for(
        quote.value,
        nifty_max=settings.nifty_max_vix,
        sensex_min=settings.sensex_min_vix,
    )
    state = State.load(settings.state_file)
    events = rules.changes(
        state.regime(),
        regime,
        nifty_max=settings.nifty_max_vix,
        sensex_min=settings.sensex_min_vix,
    )

    messages = [
        alerts.render_change(change, quote, regime, settings) for change in events
    ]
    if state.regime() is None and not args.no_announce:
        messages.insert(0, alerts.render_snapshot(quote, regime, settings))

    if args.dry_run:
        print(alerts.status_plain(quote, regime, settings))
        if not messages:
            print("\nNo threshold crossing since the last saved state.")
        for message in messages:
            print("\n--- message ---")
            print(alerts.strip_html(message))
        print(f"\n(dry run) state not written to {settings.state_file}")
        return 0

    settings.require_telegram()
    client = TelegramClient(settings.telegram_token)
    for message in messages:
        for chat_id in settings.chat_ids:
            client.send_message(chat_id, message)

    state.record(quote.value, regime, now)
    state.save(settings.state_file)

    if not args.quiet:
        print(
            f"India VIX {quote.value:.2f} · {len(messages)} message(s) sent to "
            f"{len(settings.chat_ids)} chat(s)."
        )
    return 0


def _cmd_status(settings: Settings, args: argparse.Namespace) -> int:
    quote = market.fetch_quote()
    regime = rules.regime_for(
        quote.value,
        nifty_max=settings.nifty_max_vix,
        sensex_min=settings.sensex_min_vix,
    )

    if args.json:
        payload = {
            "vix": quote.value,
            "as_of": quote.as_of.isoformat() if quote.as_of else None,
            "source": quote.source,
            "nifty_blocked": regime.nifty_blocked,
            "sensex_blocked": regime.sensex_blocked,
            "nifty_max_vix": settings.nifty_max_vix,
            "sensex_min_vix": settings.sensex_min_vix,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(alerts.status_plain(quote, regime, settings))
    return 0


def _cmd_whoami(settings: Settings) -> int:
    if not settings.telegram_token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN is missing. Add it to .env first."
        )

    client = TelegramClient(settings.telegram_token)
    me = client.get_me()
    username = me.get("username") or "your_bot"
    print(f"Bot: @{username} ({me.get('first_name') or 'unnamed'})")

    updates = client.get_updates(timeout=0)
    seen = {}
    for update in updates:
        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or {}
        )
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            continue
        name = (
            chat.get("title")
            or " ".join(
                part
                for part in (chat.get("first_name"), chat.get("last_name"))
                if part
            )
            or chat.get("username")
            or "?"
        )
        seen[chat_id] = (chat.get("type", "?"), name)

    print("")
    if not seen:
        print(
            f"No pending messages found. Open Telegram, send /start to @{username}, "
            "then run whoami again."
        )
        print(
            "Note: stop a running VIX Guard bot first — a running bot consumes "
            "incoming updates."
        )
        return 0

    for chat_id, (kind, name) in seen.items():
        print(f"{chat_id}\t{kind}\t{name}")
    print("")
    print("Put the ID(s) you want alerts in TELEGRAM_CHAT_ID, comma-separated.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        settings = Settings.from_env(args.env_file)
        _configure_logging(args.verbose, settings.log_file)

        if args.command == "run":
            return _cmd_run(settings)
        if args.command == "check":
            return _cmd_check(settings, args)
        if args.command == "status":
            return _cmd_status(settings, args)
        if args.command == "whoami":
            return _cmd_whoami(settings)
        parser.error(f"unknown command {args.command!r}")
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except market.DataUnavailable as exc:
        print(f"VIX data error: {exc}", file=sys.stderr)
        return 1
    except TelegramConflict as exc:
        print(f"Telegram conflict: {exc}", file=sys.stderr)
        return 3
    except TelegramError as exc:
        print(f"Telegram error: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130

    return 0
