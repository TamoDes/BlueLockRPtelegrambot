import logging
import sqlite3
import threading
import time

from bluelock import bot, db
from bluelock import abilities as abilities_mod
from bluelock import autoturn
from bluelock.config import (
    ADMIN_IDS,
    ADMINS,
    ABILITIES_ENABLED,
    LOBBY_SWEEP_SECONDS,
    LOBBY_TTL_HOURS,
    SEASON,
    TURN_SWEEP_SECONDS,
)
from bluelock.migrate import run as migrate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bluelock")


def sweep_lobbies() -> int:
    from bluelock import core

    cutoff = db.now() - LOBBY_TTL_HOURS * 3600
    stale = db.stale_lobbies(cutoff)
    for row in stale:
        db.update_match(row["id"], status="cancelled", ended_at=db.now())
        core.edit_view(db.match(row["id"]), "⌛ <b>LOBBY EXPIRED</b>", None)
    return len(stale)


def sweep_loop() -> None:
    while True:
        time.sleep(TURN_SWEEP_SECONDS)
        try:
            rolled = autoturn.sweep_auto_rolls()
            if rolled:
                logger.info("auto-rolled for %d AFK player(s)", rolled)
        except Exception:
            logger.exception("auto-roll sweep failed")
        if time.monotonic() % LOBBY_SWEEP_SECONDS < TURN_SWEEP_SECONDS:
            try:
                swept = sweep_lobbies()
                if swept:
                    logger.info("swept %d stale lobby/lobbies", swept)
            except Exception:
                logger.exception("lobby sweep failed")


def main() -> None:
    db.connect()
    wallets, closed, dropped = migrate()
    if wallets:
        logger.info("migrated %d legacy wallet record(s)", wallets)
    if dropped:
        logger.info("dropped inline lobby support — closed %d in-flight match(es)", closed)

    if ABILITIES_ENABLED:
        n = abilities_mod.sync_catalog()
        logger.info("ability catalog synced — %d abilities", n)

    swept = sweep_lobbies()
    if swept:
        logger.info("cleared %d stale lobby/lobbies", swept)

    threading.Thread(target=sweep_loop, daemon=True).start()

    bot.remove_webhook()
    me = bot.get_me()
    logger.info("@%s is live — season %d, %d admin(s), abilities=%s",
                me.username, SEASON, len(ADMINS) + len(ADMIN_IDS), "on" if ABILITIES_ENABLED else "off")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("bye")
    except sqlite3.Error:
        logger.exception("database error")
        raise
