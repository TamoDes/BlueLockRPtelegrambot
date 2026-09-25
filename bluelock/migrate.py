import json

from . import db
from .config import LEGACY_WALLET


def import_legacy_wallet() -> int:
    if not LEGACY_WALLET.exists():
        return 0
    try:
        data = json.loads(LEGACY_WALLET.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    usernames = data.get("usernames", {}) if isinstance(data, dict) else {}
    balances = data.get("balances", {}) if isinstance(data, dict) else {}
    pending = data.get("pending_balances", {}) if isinstance(data, dict) else {}
    moved = 0

    for uname, user_id in usernames.items():
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            continue
        db.touch_player(uid, str(uname))
        amount = int(balances.get(str(uid), 0) or 0)
        if amount:
            db.add_yen(uid, amount, "انتقال از نسخه‌ی قبلی")
            moved += 1

    for uname, amount in pending.items():
        try:
            value = int(amount or 0)
        except (TypeError, ValueError):
            continue
        if value:
            db.add_pending_yen(str(uname), value)
            moved += 1

    LEGACY_WALLET.rename(LEGACY_WALLET.with_suffix(".json.imported"))
    return moved


def close_stale_matches() -> int:
    with db.tx() as c:
        cur = c.execute(
            "UPDATE matches SET status='cancelled', phase='done', ended_at=? "
            "WHERE status IN ('open','live')",
            (db.now(),),
        )
        return cur.rowcount


def drop_inline_column() -> bool:
    with db.tx() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(matches)")]
        if "inline_id" not in cols:
            return False
        c.execute("ALTER TABLE matches DROP COLUMN inline_id")
        return True


def run() -> tuple[int, int, bool]:
    wallets = import_legacy_wallet()
    dropped = drop_inline_column()
    closed = close_stale_matches() if dropped else 0
    return wallets, closed, dropped
