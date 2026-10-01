import hashlib
import json
import time

from . import db
from .config import (
    DAILY_BASE,
    DAILY_MAX_STREAK,
    DAILY_STEP,
    QUESTS_PER_DAY,
    QUEST_REWARD,
    test_mode,
)


def local_day(ts: int | None = None) -> int:
    """Local calendar day number — 2026-09-07 and 2026-09-08 differ by exactly 1."""
    lt = time.localtime(ts if ts is not None else time.time())
    return lt.tm_year * 10000 + lt.tm_mon * 100 + lt.tm_mday


def daily_amount(streak: int) -> int:
    if test_mode():
        return 0
    return DAILY_BASE + DAILY_STEP * min(max(0, streak - 1), DAILY_MAX_STREAK - 1)


def day_gap(last_day: int, day: int) -> int:
    """Calendar days between two day-stamps — needs real dates, not arithmetic."""
    if last_day <= 0 or day <= 0:
        return 999
    y, m, d = last_day // 10000, (last_day // 100) % 100, last_day % 100
    y2, m2, d2 = day // 10000, (day // 100) % 100, day % 100
    try:
        t1 = time.mktime((y, m, d, 12, 0, 0, 0, 0, -1))
        t2 = time.mktime((y2, m2, d2, 12, 0, 0, 0, 0, -1))
    except (OverflowError, ValueError):
        return 999
    return abs(round((t2 - t1) / 86400))


def next_streak(last_day: int, streak: int, day: int) -> int:
    if last_day <= 0:
        return 1
    gap = day_gap(last_day, day)
    if gap == 1:
        return min(DAILY_MAX_STREAK, streak + 1)
    return 1


def claim(user_id: int, day: int) -> tuple[int, int] | None:
    """Returns (amount, new_streak) or None if already claimed today."""
    row = db.daily_row(user_id)
    last_day = row["last_day"] if row else 0
    streak = row["streak"] if row else 0
    new_streak = next_streak(last_day, streak, day)
    amount = daily_amount(new_streak)
    out = db.claim_daily(user_id, day, new_streak, amount, f"daily streak day {new_streak}")
    if out is None:
        return None
    return amount, new_streak


# ------------------------------------------------------------------ quests

# (id, label, target, stat key) — every quest is a threshold on a today-stat, so
# progress is always derived live from the match history. "win" is handled apart
# (needs the scoreline, not a SUM).
#
# Quests are tuned in two difficulties so a day can mix busywork with a real
# challenge: EASY quests are reachable in one or two matches, HARD ones demand a
# good day. Queues below guarantee at least one easy and at least one hard each day.
QUEST_POOL = [
    # --- easy: one match of normal play
    ("play",     "Play a match",              1,   "played"),
    ("goal",     "Score a goal",              1,   "goals"),
    ("stop",     "Make a stop",               1,   "stops"),
    ("act",      "Play 5 actions",            5,   "actions"),
    # --- medium: a decent match
    ("goal2",    "Score 2 goals",             2,   "goals"),
    ("assist",   "Make 2 assists",            2,   "assists"),
    ("stop2",    "Make 3 stops",              3,   "stops"),
    ("act2",     "Play 12 actions",           12,  "actions"),
    ("assist1",  "Make an assist",            1,   "assists"),
    # --- hard: a genuinely good day
    ("goal3",    "Hat-trick (3 goals)",       3,   "goals"),
    ("assist3",  "Make 4 assists",            4,   "assists"),
    ("stop3",    "Make 5 stops",              5,   "stops"),
    ("act3",     "Play 25 actions",           25,  "actions"),
]

QUEST_WIN = ("win", "Win a match", 1, None)      # win1/hard twin below
QUEST_WIN2 = ("win2", "Win 2 matches", 2, None)

QUEST_BY_ID = {q[0]: q for q in QUEST_POOL + [QUEST_WIN, QUEST_WIN2]}

# three fixed queue slots per day: a busywork slot, a form slot, a challenge slot
QUEST_EASY = ("play", "goal", "stop", "act", "assist1")
QUEST_MEDIUM = ("goal2", "assist", "stop2", "act2")
QUEST_HARD = ("goal3", "assist3", "stop3", "act3", "win2", "win")

QUEST_EMOJI = {
    "play": "⚔️", "goal": "⚽", "goal2": "🎯", "goal3": "🎩",
    "assist": "🅰", "assist1": "🅰", "assist3": "🅰",
    "stop": "🧱", "stop2": "🧱", "stop3": "🧱",
    "act": "🎬", "act2": "🎬", "act3": "🎬",
    "win": "🏆", "win2": "🏆",
}


def _draw(day: int, salt: int, span: int) -> int:
    """Stable pseudo-random draw: same day => same number for everyone, every run.

    Hashed per (day, salt) instead of a rolling LCG so neighbouring days are
    uncorrelated — a rolling seed made boards repeat within a week.
    """
    digest = hashlib.md5(f"{day}:{salt}".encode()).hexdigest()
    return int(digest[:8], 16) % max(1, span)


def _stat_key(qid: str) -> str:
    """Which today-stat a quest is measured on — win1/win2 share the win counter."""
    stat = QUEST_BY_ID[qid][3]
    return stat if stat is not None else "wins"


def _build_boards() -> list[tuple[str, str, str]]:
    """Every legal daily board: one easy + one medium + one hard, all different stats."""
    combos = []
    for e in QUEST_EASY:
        for m in QUEST_MEDIUM:
            for h in QUEST_HARD:
                keys = {_stat_key(e), _stat_key(m), _stat_key(h)}
                if len(keys) == 3:
                    combos.append((e, m, h))
    return sorted(combos)


QUEST_BOARDS = _build_boards()
# coprime with the board count => a day-stepped walk visits every board exactly
# once before repeating, so the board rotates through the whole catalogue.
BOARD_STEP = 37


def pick_quests(day: int) -> list[str]:
    """Stable daily board (easy + medium + hard, no repeated stat) for every player."""
    if not QUEST_BOARDS:
        return [QUEST_EASY[0], QUEST_MEDIUM[0], QUEST_HARD[0]]
    return list(QUEST_BOARDS[(day * BOARD_STEP) % len(QUEST_BOARDS)])


def quest_def(qid: str) -> tuple[str, str, int, object]:
    q = QUEST_BY_ID.get(qid)
    if q is None:
        raise KeyError(qid)
    return q


def quest_target(qid: str) -> int:
    return quest_def(qid)[2]


def today_stats(user_id: int, day: int) -> dict:
    since = day_start_ts(day)
    row = db.season_stats_since(user_id, since)
    wins = 0
    for r in db.q(
        "SELECT mp.team, m.score1, m.score2 FROM match_players mp JOIN matches m ON m.id = mp.match_id "
        "WHERE mp.user_id=? AND m.status='done' AND m.ended_at>=?",
        (user_id, since),
    ):
        mine, theirs = (r["score1"], r["score2"]) if r["team"] == 1 else (r["score2"], r["score1"])
        if mine > theirs:
            wins += 1
    return {
        "played": row["played"], "goals": row["goals"], "assists": row["assists"],
        "stops": row["stops"], "actions": row["actions"], "wins": wins,
    }


def day_start_ts(day: int) -> int:
    y, m, d = day // 10000, (day // 100) % 100, day % 100
    return int(time.mktime((y, m, d, 0, 0, 0, 0, 0, -1)))


def quest_progress(qid: str, stats: dict) -> int:
    key = quest_def(qid)[3]
    if key is None:                      # win-count quests read the scorelines
        return stats["wins"]
    return int(stats.get(key, 0))


def quest_state(user_id: int, day: int) -> dict:
    """(re)build today's quest state — progress computed live from match stats."""
    row = db.quest_row(user_id)
    if row is None or row["day"] != day:
        return {"day": day, "claimed": [], "progress": {}}
    return {"day": day, "claimed": json.loads(row["claimed"]), "progress": json.loads(row["progress"])}


def claim_quest(user_id: int, qid: str, day: int) -> int | None:
    """Pay out a finished quest. Returns amount or None if not claimable."""
    state = quest_state(user_id, day)
    if qid in state["claimed"] or qid not in pick_quests(day):
        return None
    stats = today_stats(user_id, day)
    done = quest_progress(qid, stats) >= quest_target(qid)
    if not done:
        return None
    state["claimed"].append(qid)
    db.set_quest_state(user_id, day, state["progress"], state["claimed"])
    reward = 0 if test_mode() else QUEST_REWARD
    if reward:
        db.add_yen(user_id, reward, f"quest: {quest_def(qid)[1]}")
    return reward


def quests_summary(user_id: int, day: int) -> str:
    state = quest_state(user_id, day)
    claimed = set(state["claimed"])
    stats = today_stats(user_id, day)
    lines = []
    for qid in pick_quests(day):
        _, title, target, _ = quest_def(qid)
        cur = quest_progress(qid, stats)
        mark = "✅" if qid in claimed else ("🎁" if cur >= target else "▫️")
        pips = f"{min(cur, target)}/{target}"
        lines.append(f"{mark} {QUEST_EMOJI[qid]} {title} — <code>{pips}</code>")
    return "\n".join(lines)


# ------------------------------------------------------------------ achievements

MEDALS = (
    ("first_goal", "🥇 First Blood"),
    ("hat_trick",  "🎩 Hat-Trick"),
    ("stoper",     "🧱 Wall"),
    ("five_wins",  "🏆 Blue Lock Star"),
    ("veteran",    "🎖 Veteran"),
    ("rich",       "💰 Tycoon"),
)


def medal_label(key: str) -> str:
    return next((label for k, label in MEDALS if k == key), f"🏅 {key}")


def check_and_grant(user_id: int) -> list[str]:
    """Evaluate medal conditions after a match; return newly earned medal keys."""
    from .config import SEASON

    new = []
    career = db.career(user_id)
    w, d, l = db.record(user_id)
    row = db.player(user_id)
    season_row = db.q1(
        "SELECT COALESCE(SUM(mp.stops),0) AS stops FROM match_players mp "
        "JOIN matches m ON m.id = mp.match_id WHERE mp.user_id=? AND m.status='done' AND m.season=?",
        (user_id, SEASON),
    )
    hat = db.q1(
        "SELECT COUNT(*) AS n FROM match_players mp JOIN matches m ON m.id=mp.match_id "
        "WHERE mp.user_id=? AND m.status='done' AND mp.goals>=3",
        (user_id,),
    )
    checks = [
        ("first_goal", career["goals"] >= 1),
        ("hat_trick", hat and hat["n"] >= 1),
        ("stoper", season_row and season_row["stops"] >= 10),
        ("five_wins", w >= 5),
        ("veteran", career["played"] >= 25),
        ("rich", row and row["yen"] >= 5_000_000),
    ]
    if test_mode():
        return new
    for medal, ok in checks:
        if ok and db.grant_achievement(user_id, medal):
            new.append(medal)
    return new
