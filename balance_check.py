import os
import random
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("BLUELOCK_BOT_TOKEN", "123:FAKE")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SIM_DB = ":memory:"

import bluelock.config as config

config.DB_PATH = SIM_DB
config.ABILITIES_ENABLED = False

import bluelock.db as db

db.DB_PATH = SIM_DB
db._conn = None

from bluelock import characters, engine
from bluelock.config import DICE_FACES, KEEPER_POWER, MAX_STAT, ZONE_BOX, ZONE_SHOOT, max_turns

db.connect()

NEXT_ID = iter(range(10_000, 200_000))


def d() -> int:
    return random.randint(1, DICE_FACES)


def choose(state, holder, roster):
    piece = state.get("set_piece")
    if piece:
        return piece, None
    zone = state.get("zone", 0)
    mine = engine.slot_stats(holder)
    mates = [r for r in roster if r["team"] == holder["team"] and r["slot"] != holder["slot"]]
    if zone >= ZONE_SHOOT and (zone >= ZONE_BOX or mine["shot"] >= mine["dribble"]):
        return "shoot", None
    if zone >= ZONE_BOX or (mates and mine["passing"] >= mine["dribble"]):
        if mates:
            return "pass", max(mates, key=lambda r: engine.slot_stats(r)["shot"])["slot"]
    return "dribble", None


def one_match(key_a, key_b, size, mode) -> tuple[list[int], Counter]:
    match_id = db.create_match(-1000 - random.randrange(10**9), mode, size)
    for team, key in ((1, key_a), (2, key_b)):
        stats = characters.base_stats(key)
        for i in range(size):
            uid = next(NEXT_ID)
            db.touch_player(uid, None)
            db.join_match(match_id, team, uid, f"T{team}P{i}", key, stats)
    engine.start(match_id)

    tally = Counter()
    while True:
        match = db.match(match_id)
        if engine.over(match):
            break
        roster = db.roster(match_id)
        state = engine.pending_of(match)
        holder = next(r for r in roster if r["slot"] == match["holder"])
        action, target = choose(state, holder, roster)
        db.claim_turn(match_id, match["turn"], holder["slot"])
        opened = engine.open_duel(match_id, action, target)
        assert "error" not in opened, (action, state, opened)
        while True:
            pending = engine.awaiting(db.match(match_id))
            if pending is None:
                break
            if pending["role"] in ("spot", "spot_gk"):
                engine.submit_spot(match_id, pending["user_id"], random.choice(config.PENALTY_TARGETS))
            else:
                engine.record_die(match_id, pending["role"], d())
        out = engine.resolve(match_id)
        tally[out["outcome"]] += 1

    final = db.match(match_id)
    return [final["score1"], final["score2"]], tally


def report(label, key_a, key_b, size=2, runs=200, mode="ranked"):
    scores = [0, 0]
    tally = Counter()
    actions = []
    decided = 0
    for _ in range(runs):
        s, t = one_match(key_a, key_b, size, mode)
        scores[0] += s[0]
        scores[1] += s[1]
        actions.append(sum(t.values()))
        decided += max(s) >= config.GOAL_TARGET
        tally.update(t)
    shots = tally["goal"] + tally["saved"] + tally["blocked"]
    total = sum(tally.values())
    actions.sort()
    print(
        f"{label:<22} {scores[0] / runs:.1f}-{scores[1] / runs:.1f} goals  "
        f"| actions med {actions[runs // 2]:>3} p90 {actions[int(runs * 0.9)]:>3} max {actions[-1]:>3}  "
        f"| reached {config.GOAL_TARGET}: {decided / runs:.0%}  "
        f"| conv {tally['goal'] / max(1, shots):.0%}  "
        + " ".join(f"{k}={tally[k] / total:.0%}" for k in sorted(tally))
    )


random.seed(21)
print(
    f"limits 1-{MAX_STAT}  keeper power={KEEPER_POWER}  first to {config.GOAL_TARGET}  "
    f"turn cap(2v2 ranked)={max_turns(2, 'ranked')}  dice=d{DICE_FACES}\n"
)

report("SSR rin vs SSR rin", "rin", "rin", runs=200)
report("SSR vs SR", "rin", "yukimiya", runs=200)
report("SSR vs N", "rin", "igaguri", runs=200)
report("SR vs SR", "yukimiya", "yukimiya", runs=200)
report("SR vs R", "yukimiya", "naruhaya", runs=200)
report("N vs N", "igaguri", "igaguri", runs=200)
print()
report("1v1 SSR vs SSR", "rin", "rin", size=1, runs=200)
report("3v3 SR vs SR", "yukimiya", "yukimiya", size=3, runs=150)
print()
report("friendly SR vs SR", "yukimiya", "yukimiya", runs=200, mode="friendly")

db._conn.close()
