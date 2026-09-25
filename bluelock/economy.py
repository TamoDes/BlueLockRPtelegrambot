import json
import time

from . import db
from .config import (
    DAILY_BASE,
    DAILY_MAX_STREAK,
    DAILY_STEP,
    QUESTS_PER_DAY,
    QUEST_REWARD,
)


def local_day(ts: int | None = None) -> int:
    """Local calendar day number — 2026-09-07 and 2026-09-08 differ by exactly 1."""
    lt = time.localtime(ts if ts is not None else time.time())
    return lt.tm_year * 10000 + lt.tm_mon * 100 + lt.tm_mday


def daily_amount(streak: int) -> int:
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

QUEST_POOL = [
    ("play",  "Play a match",         1, lambda s: s["played"]),
    ("goal",  "Score a goal",         1, lambda s: s["goals"]),
    ("assist","Make 2 assists",       2, lambda s: s["assists"]),
    ("stop",  "Make a stop",          1, lambda s: s["stops"]),
    ("win",   "Win a match",          1, None),
    ("act",   "Play 5 actions",       5, lambda s: s["actions"]),
]

QUEST_EMOJI = {
    "play": "⚔️", "goal": "⚽", "assist": "🅰", "stop": "🧱", "win": "🏆", "act": "🎬",
}


def pick_quests(day: int) -> list[str]:
    """Stable 3-quest rotation per day — same picks for everyone, changes daily."""
    pool = [q[0] for q in QUEST_POOL]
    seed = (day * 2654435761) % (2**32)
    out = []
    remaining = list(pool)
    for _ in range(QUESTS_PER_DAY):
        seed = (seed * 1103515245 + 12345) % (2**31)
        out.append(remaining.pop(seed % len(remaining)))
    return out


def quest_def(qid: str) -> tuple[str, str, int, object]:
    return next(q for q in QUEST_POOL if q[0] == qid)


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
    if qid == "win":
        return stats["wins"]
    return quest_def(qid)[3](stats)


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
    db.add_yen(user_id, QUEST_REWARD, f"quest: {quest_def(qid)[1]}")
    return QUEST_REWARD


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
    for medal, ok in checks:
        if ok and db.grant_achievement(user_id, medal):
            new.append(medal)
    return new
