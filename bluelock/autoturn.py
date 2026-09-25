import logging
import random

from . import db, engine
from .config import AUTO_ROLL_SECONDS, PENALTY_TARGETS
from .core import broadcast

logger = logging.getLogger("bluelock")


def sweep_auto_rolls() -> int:
    """Roll the dice (or pick a corner) for players idle past the timer."""
    from . import handlers_match

    acted = 0
    for m in db.open_matches():
        if m["status"] != "live" or m["phase"] != "duel":
            continue
        match = db.match(m["id"])
        if not match:
            continue
        state = engine.pending_of(match)
        waited = engine.stale_since(state, match)
        if waited is None or waited < AUTO_ROLL_SECONDS:
            continue
        pending = engine.awaiting(match)
        if pending is None or pending["role"] == "gk" or pending["user_id"] is None:
            continue
        if auto_fill(match, pending):
            acted += 1
            handlers_match.advance(match["id"])
    return acted


def auto_fill(match, pending: dict) -> bool:
    """Bot plays on behalf of an idle player; True when the action landed."""
    match_id = match["id"]
    user_id = pending["user_id"]
    role = pending["role"]
    name = pending["name"]

    if role in ("att", "def"):
        value = random.randint(1, 6)
        result = engine.submit_die(match_id, user_id, value)
        if result.get("status") != "ok":
            return False
        broadcast(match, f"⏱ <b>{name}</b> was AFK — the bot rolled <b>{value}</b> for them.")
        db.log_event(match_id, f"⏱ Bot rolled <b>{value}</b> for <b>{name}</b> (AFK).")
        return True

    if role == "spot":
        corner = random.choice(PENALTY_TARGETS)
        result = engine.submit_spot(match_id, user_id, corner)
        if result.get("status") != "ok":
            return False
        broadcast(match, f"⏱ <b>{name}</b> was AFK — the bot locked a corner for them.")
        db.log_event(match_id, f"⏱ Bot picked a corner for <b>{name}</b> (AFK).")
        return True

    if role == "spot_gk":
        corner = random.choice(PENALTY_TARGETS)
        result = engine.submit_spot(match_id, user_id, corner)
        if result.get("status") != "ok":
            return False
        broadcast(match, f"⏱ <b>{name}</b> was AFK — the bot called the dive for them.")
        db.log_event(match_id, f"⏱ Bot called the dive for <b>{name}</b> (AFK).")
        return True

    return False
