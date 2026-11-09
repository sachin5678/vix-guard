# VIX Guard

Telegram alerts for the India VIX filters in the NIFTY / SENSEX STBT playbook.

| India VIX | What happens |
| --- | --- |
| **Above 22** | 🔴 Stop **NIFTY STBT** |
| **Below 11** | 🔴 Stop **SENSEX STBT** |
| **11 – 22** | ✅ Both allowed |

VIX Guard checks India VIX every 5 minutes during market hours and sends:

- a **STOP** message the moment a line is crossed,
- a **BACK ON** message when the condition clears,
- a daily **plan** before the open (optional),
- a warning if the VIX feed itself goes down.

It also remembers the last regime, so restarting the bot does not re-send
alerts you already received.

**No pip packages.** Python 3.9+ and the standard library are enough.

---

## Sample alerts

```text
🔴 STOP — NIFTY STBT

India VIX 22.41 — above 22.
As of 09 Nov 2026, 10:35 IST · Yahoo Finance

Rule
never run NIFTY STBT when VIX is above 22

Do
skip NIFTY STBT · no overnight NIFTY shorts

NIFTY STBT — ❌ OFF
SENSEX STBT — ✅ ON
```

```text
🔴 STOP — SENSEX STBT

India VIX 10.86 — below 11.
As of 09 Nov 2026, 11:05 IST · Yahoo Finance

Rule
never run SENSEX STBT when VIX is below 11

Do
skip SENSEX STBT · no overnight SENSEX shorts

NIFTY STBT — ✅ ON
SENSEX STBT — ❌ OFF
```

When VIX moves back into the safe zone, the bot sends `🟢 BACK ON — NIFTY STBT`
or `🟢 BACK ON — SENSEX STBT` with both strategy states.

---

## Quick start

```powershell
cd E:\Desktop\YT\vix-guard
copy .env.example .env
notepad .env
```

Fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then:

```powershell
python -m vixguard status   # verify the VIX feed
python -m vixguard run      # start watching
```

On startup the bot sends one status message to your chat. After that it is
silent unless a threshold flips.

---

## 1. Create the Telegram bot

1. In Telegram, message **@BotFather**.
2. Send `/newbot`, choose a name and a username (for example `VixGuardBot`).
3. Copy the **token** (looks like `123456789:AAH...`).
4. Open your new bot and send it `/start`.
5. Put the token in `.env` as `TELEGRAM_BOT_TOKEN`.

The token is a password. Never commit `.env` or paste the token into a chat.
`.gitignore` already excludes `.env`.

## 2. Find your chat ID

```powershell
python -m vixguard whoami
```

It prints something like:

```text
Bot: @VixGuardBot (VIX Guard)
123456789	private	Your Name

Put the ID(s) you want alerts in TELEGRAM_CHAT_ID, comma-separated.
```

Copy that number into `TELEGRAM_CHAT_ID`. For a group, add the bot to the
group, send `/start@YourBot` there, then run `whoami` again. Group IDs are
negative, for example `-1001234567890`.

`whoami` only sees pending messages. If it prints "No pending messages",
send `/start` to the bot again and rerun it. Stop a running VIX Guard bot
first: a running bot consumes incoming updates.

Multiple chats are allowed:

```env
TELEGRAM_CHAT_ID=123456789,-1001234567890
```

## 3. Check the data feed

```powershell
python -m vixguard status
```

```text
VIX Guard — status
India VIX 18.43
As of 08 Nov 2026, 15:30 IST · Yahoo Finance

NIFTY STBT  : ON   (off above 22)
SENSEX STBT : ON   (off below 11)

Both ON when VIX is between 11 and 22.
```

Use `--json` for scripting:

```powershell
python -m vixguard status --json
```

## 4. Run the bot

```powershell
python -m vixguard run
```

Keep the window open. `Ctrl+C` stops it. For unattended running see
[Deployment](#deployment).

To check the full pipeline without sending anything or touching state:

```powershell
python -m vixguard check --dry-run --force
```

---

## Commands

| Command | What it does |
| --- | --- |
| `/status` | Current India VIX, both strategy states, data timestamp |
| `/vix` | Just the current India VIX |
| `/rules` | Your thresholds |
| `/id` | The current chat's ID |
| `/help` | Help text |
| `/ping` | Liveness check |

Commands only work from chat IDs listed in `TELEGRAM_CHAT_ID`. `/help`, `/id`
and `/ping` work from any chat so setup is easy.

---

## Configuration

All settings live in `.env` (see `.env.example`). Real environment variables
win over `.env`, which is handy for Docker and systemd.

| Variable | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | — | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | — | One or more chat IDs, comma-separated |
| `NIFTY_MAX_VIX` | `22` | NIFTY STBT is off when VIX is **above** this |
| `SENSEX_MIN_VIX` | `11` | SENSEX STBT is off when VIX is **below** this |
| `POLL_SECONDS` | `300` | Seconds between checks (minimum 15) |
| `STATE_FILE` | `state.json` | Where the last regime is remembered |
| `ANNOUNCE_ON_START` | `true` | Send a status message at startup |
| `DAILY_DIGEST` | `true` | Send a plan before the open, once per trading day |
| `DIGEST_AFTER` | `09:10` | Earliest digest time, IST |
| `MARKET_OPEN` | `09:05` | Polling window starts, IST |
| `MARKET_CLOSE` | `15:40` | Polling window ends, IST |
| `LOG_FILE` | — | Optional rotating log file (2 MB × 3) |

Thresholds must satisfy `0 < SENSEX_MIN_VIX < NIFTY_MAX_VIX`. The bot validates
this at startup and refuses to run with a nonsensical configuration.

After changing `.env`, restart the bot.

---

## How it decides

The rule is evaluated exactly as stated:

- NIFTY STBT is blocked when `VIX > 22`.
- SENSEX STBT is blocked when `VIX < 11`.
- Exactly `22.00` or `11.00` is allowed, because the rule says *above* / *below*.

A message is sent only when the *regime* changes, not on every poll. The saved
state holds `nifty_blocked` and `sensex_blocked`, so:

- first run: baseline, no crossing alert (a status snapshot is sent instead),
- 21 → 23: `STOP — NIFTY STBT`,
- 23 → 21: `BACK ON — NIFTY STBT`,
- 12 → 10: `STOP — SENSEX STBT`,
- 10 → 12: `BACK ON — SENSEX STBT`.

If the feed fails three times in a row, the bot sends one warning and pauses
alerts. When the feed recovers, it sends a short "feed back" message.

---

## Deployment

### Windows Task Scheduler

Use this if the PC is on during market hours.

1. Open **Task Scheduler** → **Create Task**.
2. **General**: name it `VIX Guard`, choose "Run whether user is logged on or not".
3. **Triggers**: New → **At log on** (and/or Daily at 09:00).
4. **Actions**: New → Start a program:
   - Program: `E:\Desktop\YT\vix-guard\run.bat`
   - Start in: `E:\Desktop\YT\vix-guard`
5. **Settings**: enable "Restart the task if it fails", every 1 minute, 3 times.
6. Save and right-click → **Run** to test.

For logs, run the command directly from a terminal:

```powershell
python -m vixguard run >> logs\vixguard.log 2>&1
```

Create the `logs` folder first.

### Cron-style checks (no long-running process)

If the machine is not always on, schedule `run-check.bat` instead. It runs one
check, sends only real threshold crossings, saves state, and exits. It does not
send the daily digest.

Task Scheduler setup:

1. Create Task → **Triggers** → New → **Weekly** → Mon–Fri, 09:00.
2. In the same trigger, tick **Repeat task every 5 minutes** for **6 hours 45 minutes**.
3. **Actions** → `E:\Desktop\YT\vix-guard\run-check.bat`.
4. **Start in**: `E:\Desktop\YT\vix-guard`.

Keep `state.json` on a persistent disk. If it is lost, the next run treats
itself as a first run and sends a snapshot rather than a crossing alert.

### Linux (systemd)

```ini
# /etc/systemd/system/vix-guard.service
[Unit]
Description=VIX Guard Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/vix-guard
ExecStart=/usr/bin/python3 -m vixguard run
EnvironmentFile=/opt/vix-guard/.env
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vix-guard
sudo journalctl -u vix-guard -f
```

Only one instance may poll a bot token at a time. A second instance exits with
a clear conflict message.

### GitHub

The private repository lives at
<https://github.com/sachinpatilgit/vix-guard> and the public mirror at
<https://github.com/sachin5678/vix-guard>. The local clone has `origin`
configured for the private repository, so publishing a change is:

```bash
git push
```

### Docker

```bash
docker build -t vix-guard .
docker run -d --name vix-guard --restart unless-stopped \
  --env-file .env \
  -e STATE_FILE=/data/state.json \
  -v vixguard-data:/data \
  vix-guard
```

```bash
docker logs -f vix-guard
```

---

## CLI reference

```text
python -m vixguard run                 Run the Telegram bot
python -m vixguard check               One check; sends alerts, saves state
python -m vixguard check --dry-run     Print what would be sent; no state change
python -m vixguard check --force       Check outside market hours
python -m vixguard check --no-announce Skip the first-run snapshot
python -m vixguard status              Human-readable status
python -m vixguard status --json       JSON status
python -m vixguard whoami              Print chat IDs from pending messages
```

Exit codes: `0` success, `1` VIX data error, `2` configuration error,
`3` Telegram error, `130` interrupted.

---

## Data source and limitations

- The quote comes from the Yahoo Finance chart endpoint for `^INDIAVIX`.
  NSE's own API rejects scripted clients with HTTP 403, so it is not used.
- Yahoo can lag the exchange by a few minutes. Every message shows the exact
  quote timestamp, so you can see how fresh it is. This is a regime guard,
  not a tick-by-tick trigger.
- Only weekends are skipped automatically. On exchange holidays the last price
  does not move, so no crossing fires and no daily digest is sent (the digest
  requires a quote timestamp from today).
- During market hours a quote older than 4 hours is ignored, so a pre-open run
  waits for the first live print instead of acting on yesterday's close.
- The bot does not place, modify or cancel orders. It only reminds you.
- Keep the machine awake during market hours if you use `run` mode. Otherwise
  use the scheduled `check` mode on a small always-on VPS.

---

## Tests

```powershell
python -m unittest discover -s tests -t . -v
```

56 tests cover the threshold boundaries, regime transitions, state persistence,
Yahoo payload parsing, message rendering and configuration validation.

---

## Project layout

```text
vix-guard/
├── vixguard/
│   ├── alerts.py      message rendering (Telegram HTML + plain text)
│   ├── bot.py         long polling, schedule, commands
│   ├── cli.py         run / check / status / whoami
│   ├── config.py      .env parsing and validation
│   ├── market.py      India VIX fetch + Yahoo parser
│   ├── net.py         tiny urllib JSON helper
│   ├── rules.py       pure threshold logic
│   ├── state.py       atomic JSON state
│   └── telegram.py    minimal Bot API client
├── tests/
├── .env.example
├── Dockerfile
├── run.bat            run the bot
└── run-check.bat      one-shot check for Task Scheduler
```

---

## Disclaimer

Not investment advice. The thresholds come from your backtest. Verify the data
and the rule before risking money, and keep your own kill switch.
