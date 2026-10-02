# Deploying on Railway

The bot runs as a **worker** (Telegram long-polling — no inbound port, no
webhook, no healthcheck URL).

## Steps

1. **New project → Deploy from GitHub repo** → pick `TamoDes/BlueLockRPtelegrambot`.
   Railway detects Python via `requirements.txt` (Nixpacks) and starts it with
   `python main.py` (see `railway.toml`).
2. **Settings → Service → add a Volume:**
   - Mount path: `/data`
   - Size: at least 1 GB
   Without a volume the SQLite file lives inside the container and **all
   player data is wiped on every redeploy**.
3. **Settings → Variables:**
   - `BLUELOCK_BOT_TOKEN` — from @BotFather (required; the bot exits without it)
   - `BLUELOCK_DB_PATH` = `/data/bluelock.db` — points the database onto the volume
   - `BLUELOCK_ADMINS` — optional, comma-separated usernames (no @)
4. **Settings → Service → Service Type = Worker** (not HTTP).
5. Deploy. First boot runs the SQLite migrations automatically and logs
   `@<botname> is live — season …`.

## Rules / gotchas

- **Exactly 1 replica.** Two instances would both poll Telegram and fight
  over one SQLite file.
- `restartPolicy = "on_failure"` — a crashed process is restarted by Railway.
- Local runs are untouched: without `BLUELOCK_DB_PATH` the database stays at
  `./bluelock.db` exactly as before.
- The repo's `.env` (local only, git-ignored) is read as a fallback when the
  Railway variables are not set; on Railway the dashboard variables win.
