import json
import os
import random
import sys
import threading
from pathlib import Path

os.environ.setdefault("BLUELOCK_BOT_TOKEN", "123:FAKE")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TEST_DB = HERE / "test_sim.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(TEST_DB) + suffix).unlink(missing_ok=True)

import bluelock.config as config

config.DB_PATH = TEST_DB
config.ABILITIES_ENABLED = False

import bluelock.db as db

db.DB_PATH = TEST_DB
db._conn = None

from bluelock import abilities, characters, engine, payouts, views
from bluelock.config import (
    DICE_FACES,
    GOAL_TARGET,
    KEEPER_CATCH_ROLL,
    KEEPER_POWER,
    ZONE_BOX,
    ZONE_SHOOT,
    max_turns,
)

db.connect()

USERS = [(101, "alpha"), (102, "beta"), (103, "gamma"), (104, "delta")]
for uid, uname in USERS:
    db.touch_player(uid, uname)
    assert db.set_display(uid, uname.capitalize())

for (uid, _), key in zip(USERS, ["kira", "yuki", "naruhaya", "hyoma_k"]):
    db.assign_char(uid, key)

assert db.set_display(102, "Alpha") is False

db.bump_boost(101, "shot", 9)
own = db.owned_by(101)
eff = characters.effective_stats(own["char_key"], json.loads(own["boosts"]))
assert eff["shot"] == min(config.MAX_STAT, characters.base_stats(own["char_key"])["shot"] + config.MAX_BOOST)
assert all(1 <= v <= config.MAX_STAT for v in eff.values())
assert 1 <= KEEPER_POWER <= config.MAX_STAT
assert 1 < KEEPER_CATCH_ROLL <= DICE_FACES

assert config.level_for(0) == 1
assert config.xp_for_level(1) == 0
for lvl in range(1, config.MAX_LEVEL):
    need = config.xp_for_level(lvl)
    assert config.level_for(need) == lvl, (lvl, need, config.level_for(need))
    assert config.level_for(need - 1) == lvl - 1 or lvl == 1
    assert config.xp_for_level(lvl + 1) > need
assert config.level_for(10**9) == config.MAX_LEVEL
assert config.boosts_allowed(1) == 0
assert config.boosts_allowed(config.BOOST_LEVELS[0]) == 1
assert config.boosts_allowed(config.BOOST_LEVELS[-1]) == len(config.BOOST_LEVELS)

ovrs = {k: characters.overall(characters.base_stats(k)) for k in characters.ROSTER}
assert all(1 <= v <= 99 for v in ovrs.values())
assert ovrs["rin"] > ovrs["yukimiya"] > ovrs["igaguri"]
assert characters.overall({s: config.MAX_STAT for s in config.STATS}) == 99
print("ovr range:", min(ovrs.values()), "-", max(ovrs.values()))

match_id = db.create_match(-100500, "ranked", 2)
for i, (uid, uname) in enumerate(USERS):
    o = db.owned_by(uid)
    stats = characters.effective_stats(o["char_key"], json.loads(o["boosts"]))
    db.join_match(match_id, 1 if i < 2 else 2, uid, uname.capitalize(), o["char_key"], stats)

db.touch_player(999, "extra")
assert db.join_match(match_id, 1, 999, "Extra", None, {}) == "full"
assert db.join_match(match_id, 1, 101, "Alpha", None, {}) == "already"
print(views.lobby_text(db.match(match_id), db.roster(match_id)))
print("=" * 46)

assert engine.start(match_id) is True
assert engine.start(match_id) is False

random.seed(11)
guard = 0
goals_seen = 0
fouls_seen = 0
saves_seen = 0
blocks_seen = 0
beaten_seen = 0
pieces_seen = set()

while True:
    m = db.match(match_id)
    if engine.over(m):
        break
    guard += 1
    assert guard < 400, "runaway loop"

    state = engine.pending_of(m)
    zone = state.get("zone", 0)
    roster = db.roster(match_id)
    holder = next(r for r in roster if r["slot"] == m["holder"])
    legal = engine.legal_actions(m)
    piece = state.get("set_piece")

    assert ("dribble" in legal) == (zone < ZONE_BOX and not piece)
    assert ("shoot" in legal) == (zone >= ZONE_SHOOT and not piece)
    if piece == "penalty":
        assert legal == ["penalty"]
    elif piece == "freekick":
        assert legal == ["freekick", "cross"]
        piece = random.choice(["freekick", "cross"])

    if piece:
        action, target = piece, None
        pieces_seen.add("freekick" if piece == "cross" else piece)
    elif "shoot" in legal and guard % 3 == 0:
        action, target = "shoot", None
    elif "dribble" in legal and guard % 2:
        action, target = "dribble", None
    else:
        mates = [r for r in roster if r["team"] == holder["team"] and r["slot"] != holder["slot"]]
        action, target = ("pass", mates[0]["slot"]) if mates else ("shoot", None)

    for bad in ("dribble", "shoot", "freekick", "penalty"):
        if bad not in legal and bad != piece:
            assert "error" in engine.open_duel(match_id, bad, None), f"{bad} must be rejected in zone {zone}"

    if action in ("pass", "cross") and not target:
        mates = [r for r in roster if r["team"] == holder["team"] and r["slot"] != holder["slot"]]
        target = mates[0]["slot"]

    assert db.claim_turn(match_id, m["turn"], holder["slot"]) is True
    opened = engine.open_duel(match_id, action, target)
    assert "error" not in opened, opened

    m = db.match(match_id)
    assert m["phase"] == "duel"
    duel = engine.pending_of(m)["duel"]
    shown = characters.effective_stats(
        holder["char_key"], json.loads(db.owned_by(holder["user_id"])["boosts"])
    )
    assert duel["att_power"] == max(1, shown[engine.ACTION_STAT[action]])
    if action in engine.SET_PIECES:
        assert duel["defender"] is None, "direct set pieces are unopposed by field players"
    elif action == "cross":
        assert duel["defender"] is not None, "a cross is contested by the wall marker"
    elif duel["defender"] is not None:
        marker_row = next(r for r in roster if r["slot"] == duel["defender"])
        assert duel["def_power"] == engine.slot_stats(marker_row)["meta"]
        assert duel["defender"] not in state.get("beaten", []), "beaten defender must not mark again"
    else:
        opponents = {r["slot"] for r in roster if r["team"] != holder["team"]}
        assert opponents <= set(state.get("beaten", [])), "only unmarked when every opponent is beaten"
    if action in engine.KEEPER_ACTIONS:
        assert duel["gk_power"] == KEEPER_POWER, (action, duel["gk_power"], KEEPER_POWER)
    else:
        assert duel["gk_power"] == 0

    pending = engine.awaiting(m)
    if action == "penalty":
        assert pending["role"] == "spot"
    elif action == "cross":
        assert pending["role"] == "att"
    elif duel["defender"] is None and action in ("pass", "dribble"):
        assert pending is None, "unmarked pass/dribble needs no dice"
        assert duel.get("no_dice") is True
    else:
        assert pending["role"] == "att"
        assert pending["user_id"] == holder["user_id"]
        assert engine.submit_die(match_id, 999, 3)["status"] == "wrong", "outsider can't roll"
        assert engine.submit_die(match_id, holder["user_id"], random.randint(1, DICE_FACES))["status"] == "ok"

    seen_roles = []
    while True:
        m = db.match(match_id)
        pending = engine.awaiting(m)
        if pending is None:
            break
        seen_roles.append(pending["role"])
        if pending["role"] == "gk":
            assert pending["name"] == config.KEEPER_NAME
            assert engine.submit_die(match_id, holder["user_id"], 6)["status"] == "keeper"
            assert engine.record_die(match_id, "gk", random.randint(1, DICE_FACES)) is True
        elif pending["role"] in ("spot", "spot_gk"):
            assert engine.record_die(match_id, "att", 6) is False, "penalty has no dice"
            assert engine.submit_spot(match_id, pending["user_id"], random.choice(config.PENALTY_TARGETS))["status"] == "ok"
        else:
            assert engine.record_die(match_id, "gk", 6) is False, "keeper can't jump the queue"
            assert engine.submit_die(match_id, pending["user_id"], random.randint(1, DICE_FACES))["status"] == "ok"

    if "gk" in seen_roles:
        assert seen_roles.index("gk") == len(seen_roles) - 1, "keeper rolls last"

    m = db.match(match_id)
    assert engine.ready(m) is True
    out = engine.resolve(match_id)
    assert out is not None
    assert engine.resolve(match_id) is None, "duel must resolve exactly once"
    if out["defender"] is None and out["action"] in ("pass", "dribble"):
        assert out.get("walked") is True, "unmarked open play must resolve dice-free"

    if out["outcome"] == "goal":
        goals_seen += 1
        if out["action"] == "penalty":
            assert out["att_spot"] != out["gk_spot"] or out.get("nerve") == "won"
        else:
            assert out["att_total"] > out["gk_total"], (out["att_total"], out["gk_total"])
            assert out["defender"] is None or out["att_total"] > out["def_total"]
    if out["outcome"] == "saved":
        saves_seen += 1
        if out["action"] == "penalty":
            assert out["att_spot"] == out["gk_spot"] and out.get("nerve") == "lost"
        else:
            assert out["att_total"] <= out["gk_total"]
        assert db.match(match_id)["holder"] == out["receiver"]["slot"]
    if out["outcome"] == "blocked":
        blocks_seen += 1
        if out["action"] != "shoot":
            assert out["att_total"] < out["def_total"]
            assert out["gk_die"] is None, "no keeper roll when the marker wins"
        else:
            # wall block: the failing defender's roll decides, snapshot def_total is the best marker's
            loser = next(
                (r for r in out.get("wall_rolls", [])
                 if out["att_total"] <= r["die"] + out["def_power"]),
                None,
            )
            assert loser is not None or out["att_total"] < out["def_total"]
            assert out["gk_die"] is None, "no keeper roll when the wall wins"
    if out["outcome"] == "foul":
        fouls_seen += 1
        assert out["reason"] == "deadlock", "set pieces now come only from exact-tie deadlocks"
        assert out["att_total"] == out["def_total"], "deadlock means exact totals"
        expected_piece = "penalty" if out["zone"] >= ZONE_BOX else "freekick"
        assert out["set_piece"] == expected_piece, (out["zone"], out["set_piece"])
        assert out["action"] not in engine.SET_PIECES, "set pieces cannot award another set piece"
        assert engine.pending_of(db.match(match_id))["set_piece"] == out["set_piece"]

    after = engine.pending_of(db.match(match_id))
    assert 0 <= after["zone"] <= ZONE_BOX
    if out["outcome"] in ("pass_ok", "dribble_ok") and out["defender"] is not None:
        assert out["defender"]["slot"] in after["beaten"], "beaten marker must be logged"
    if out["outcome"] in ("intercepted", "tackled", "blocked", "saved"):
        assert out["actor"]["slot"] in after["beaten"], "the beaten actor stays loose after a turnover"
    if out["outcome"] == "goal":
        assert after["beaten"] == [], "a goal is not a loss — nobody stays loose"
    if out["outcome"] == "foul":
        assert after["beaten"] == [], "a set piece resets the beaten list"
    if out["outcome"] == "dribble_ok":
        assert after["last_pass"] is None, "a dribble can't leave a stale assist"
    beaten_seen = max(beaten_seen, len(after.get("beaten", [])))
    db.log_event(match_id, engine.describe(out, {r["slot"]: r for r in db.roster(match_id)}))

    if guard == 1:
        print(engine.describe(out))
        print("=" * 46)

print(views.scoreboard(db.match(match_id), db.roster(match_id)))
print("=" * 46)
final = db.match(match_id)
print(f"goals={goals_seen} saves={saves_seen} blocks={blocks_seen} fouls={fouls_seen} actions={guard}")
print("set pieces taken:", sorted(pieces_seen))
print(f"ranked ended {final['score1']}-{final['score2']} after {guard} actions")
assert fouls_seen > 0, "clumsy-defender fouls should occur without a referee"
assert saves_seen + blocks_seen > 0, "shots must be stopped somewhere"
assert beaten_seen > 0, "the beaten-defender list should fill during attacks"
assert pieces_seen, "at least one set piece should have been taken"
assert engine.over(final), "match must reach a decision"
target_hit = max(final["score1"], final["score2"]) >= GOAL_TARGET
turn_capped = final["turn"] > max_turns(final["size"], "ranked")
assert target_hit ^ turn_capped, "exactly one end condition decides the match"
assert engine.turn_limit(final) == max_turns(final["size"], "ranked") > max_turns(final["size"], "friendly")

before_yen = {uid: db.player(uid)["yen"] for uid, _ in USERS}
report, level_ups = payouts.settle(match_id)
print(report)
assert payouts.settle(match_id) is None
assert report.count("•") <= config.RECAP_KEEP, "recap must be capped"
print("=" * 46)

for uid, _ in USERS:
    row = db.player(uid)
    assert row["yen"] > before_yen[uid]
    assert row["xp"] > 0
for uid, old, new in level_ups:
    assert new > old
    assert config.level_for(db.player(uid)["xp"]) == new

print(views.profile_text(db.player(101)))
print("=" * 46)
print(views.card_text(db.player(102)))
print("=" * 46)
print(views.keeper_card())
print("=" * 46)
print(views.rules_text())
print("=" * 46)
print(views.leaderboard_text("goals"))
print("=" * 46)

duel_match = db.create_match(-777, "friendly", 1)
for uid, team in ((101, 1), (103, 2)):
    o = db.owned_by(uid)
    db.join_match(duel_match, team, uid, f"P{uid}", o["char_key"],
                  characters.effective_stats(o["char_key"], json.loads(o["boosts"])))
assert engine.start(duel_match) is True
m = db.match(duel_match)
holder = next(r for r in db.roster(duel_match) if r["slot"] == m["holder"])
assert db.claim_turn(duel_match, m["turn"], holder["slot"]) is True
assert "error" not in engine.open_duel(duel_match, "dribble", None)
assert db.live_duel_in(-777)["id"] == duel_match
engine.cancel_duel(duel_match)
assert db.match(duel_match)["phase"] == "play"
assert db.live_duel_in(-777) is None
assert "error" in engine.open_duel(duel_match, "penalty", None), "no set piece without a foul"
assert "error" in engine.open_duel(duel_match, "shoot", None), "no shooting from the opening zone"

pm_match = db.create_match(101, "friendly", 1)
for uid, team in ((101, 1), (103, 2)):
    o = db.owned_by(uid)
    db.join_match(pm_match, team, uid, f"PM{uid}", o["char_key"],
                  characters.effective_stats(o["char_key"], json.loads(o["boosts"])))
db.add_view(pm_match, 103, 5001)
db.add_view(pm_match, 103, 5002)
assert [dict(r) for r in db.views_of(pm_match)] == [{"chat_id": 103, "message_id": 5002}]
assert db.match_of_user(103)["id"] == pm_match
assert engine.start(pm_match) is True

m = db.match(pm_match)
holder = next(r for r in db.roster(pm_match) if r["slot"] == m["holder"])
assert db.claim_turn(pm_match, m["turn"], holder["slot"]) is True
assert "error" not in engine.open_duel(pm_match, "dribble", None)
assert db.live_duel_in(103)["id"] == pm_match, "views must see the duel too"
engine.cancel_duel(pm_match)


def stage(mid: int, holder_slot: int, **kw) -> None:
    state = engine.fresh_state()
    state.update(kw)
    db.update_match(mid, pending=json.dumps(state), phase="opening", holder=holder_slot)


taker = next(r for r in db.roster(pm_match) if r["user_id"] == 101)

stage(pm_match, taker["slot"], set_piece="penalty", zone=ZONE_BOX)
opened = engine.open_duel(pm_match, "penalty", None)
assert "error" not in opened
assert opened["defender"] is None, "penalty is keeper only"
assert engine.legal_actions(db.match(pm_match)) == ["penalty"]
pending = engine.awaiting(db.match(pm_match))
assert pending["role"] == "spot", pending["role"]
assert engine.record_die(pm_match, "att", 6) is False, "penalty has no attack die"
assert engine.submit_spot(pm_match, 999, "left")["status"] == "wrong"
assert engine.submit_spot(pm_match, 103, "left")["status"] == "wrong", "wrong user"
assert engine.submit_spot(pm_match, 101, "left")["status"] == "ok"
pending = engine.awaiting(db.match(pm_match))
assert pending["role"] == "spot_gk"
assert engine.submit_spot(pm_match, 101, "center")["status"] == "wrong", "the dive is the defending side's call"
assert engine.submit_spot(pm_match, 103, "right")["status"] == "ok"
assert engine.ready(db.match(pm_match))
out = engine.resolve(pm_match)
assert out["outcome"] == "goal", out
assert out["att_spot"] == "left" and out["gk_spot"] == "right"
assert out["def_die"] is None and out["def_power"] == 0
assert engine.duel_line(out) == ""
print(engine.describe(out))

stage(pm_match, taker["slot"], set_piece="penalty", zone=ZONE_BOX)
engine.open_duel(pm_match, "penalty", None)
engine.submit_spot(pm_match, 101, "center")
engine.submit_spot(pm_match, 103, "center")
out = engine.resolve(pm_match)
assert out["outcome"] in ("goal", "saved"), out
assert out["att_spot"] == "center" and out["gk_spot"] == "center"
if out["outcome"] == "saved":
    assert out["nerve"] == "lost" and out["pen_sho"] < out["pen_gk"]
else:
    assert out["nerve"] == "won" and out["pen_sho"] >= out["pen_gk"]
print(engine.describe(out))

stage(pm_match, taker["slot"], set_piece="freekick", zone=1)
opened = engine.open_duel(pm_match, "freekick", None)
assert "error" not in opened
assert opened["defender"] is None, "a direct free kick faces the wall-backed keeper alone"
roles = []
while True:
    pending = engine.awaiting(db.match(pm_match))
    if pending is None:
        break
    roles.append(pending["role"])
    if pending["role"] == "gk":
        assert engine.record_die(pm_match, "gk", 3) is True
    else:
        assert engine.submit_die(pm_match, pending["user_id"], 6)["status"] == "ok"
assert roles == ["att", "gk"], roles
out = engine.resolve(pm_match)
assert out["outcome"] in ("goal", "saved"), out
assert engine.pending_of(db.match(pm_match)).get("set_piece") is None, "a free kick can't award another"
print(engine.describe(out))
db.drop_view(pm_match, 103)
assert db.views_of(pm_match) == []
print("=" * 46)

# --- ADVANCE: unmarked open play walks a zone without dice ------------------
adv_match = db.create_match(-888, "friendly", 1)
for uid, team in ((101, 1), (103, 2)):
    o = db.owned_by(uid)
    db.join_match(adv_match, team, uid, f"AD{uid}", o["char_key"],
                  characters.effective_stats(o["char_key"], json.loads(o["boosts"])))
assert engine.start(adv_match) is True
adv_holder = next(r for r in db.roster(adv_match) if r["user_id"] == 101)
foe_slot = next(r["slot"] for r in db.roster(adv_match) if r["user_id"] == 103)
turn0 = db.match(adv_match)["turn"]

stage(adv_match, adv_holder["slot"], zone=0, beaten=[foe_slot])
db.update_match(adv_match, phase="play")  # advance claims only from the play phase

marked = engine.marker(db.roster(adv_match), adv_holder["team"], [foe_slot])
assert marked is None, "with the only foe beaten nobody marks the holder"
assert db.claim_walk(adv_match, turn0, adv_holder["slot"]) is True
assert db.claim_walk(adv_match, turn0, adv_holder["slot"]) is False, "advance consumes the turn exactly once"
mid_walk = db.match(adv_match)
assert mid_walk["turn"] == turn0 + 1, (mid_walk["turn"], turn0)
st = engine.pending_of(mid_walk)
st["zone"] = 1  # mirror the handler's zone bump — db layer only guards the turn
st["last_pass"] = None
db.update_match(adv_match, pending=json.dumps(st))
after = engine.pending_of(db.match(adv_match))
assert after["zone"] == 1 and after["last_pass"] is None, after.get("zone")
assert after.get("duel") is None
print("ok  advance: unmarked walk zone+1, no duel, single-use turn claim")

# marked holder must NOT be able to walk — the handler's marker() guard, checked at engine level
stage(adv_match, adv_holder["slot"], zone=0, beaten=[])
db.update_match(adv_match, phase="play")
turn1 = db.match(adv_match)["turn"]
assert engine.marker(db.roster(adv_match), adv_holder["team"], []) is not None, "an un-beaten foe marks the holder"
assert engine.marker(db.roster(adv_match), adv_holder["team"], [foe_slot]) is None, "beaten foe does not mark"
assert db.match(adv_match)["turn"] == turn1
print("ok  advance marker guard distinguishes beaten vs marked")

db._conn.execute("DELETE FROM matches WHERE id=?", (adv_match,))
db._conn.commit()
print("=" * 46)

# --- KICKOFF: from the back, alternating teams ------------------------------
# both matches share one chat_id so the alternation can see the previous kickoff
kb1 = db.create_match(-700, "friendly", 2)
kb2 = db.create_match(-700, "friendly", 2)
for mid_kb in (kb1, kb2):
    for uid, team in ((101, 1), (102, 1), (103, 2), (104, 2)):
        o = db.owned_by(uid)
        db.join_match(mid_kb, team, uid, f"KB{uid}", o["char_key"],
                      characters.effective_stats(o["char_key"], json.loads(o["boosts"])))
assert engine.start(kb1) is True
m1 = db.match(kb1)
lines1 = engine.initial_lines(db.roster(kb1))
opener1 = next(r for r in db.roster(kb1) if r["slot"] == m1["holder"])
assert lines1[opener1["slot"]] == 2, "kickoff starts from the deepest lane (Back)"
first_team = opener1["team"]
assert engine.start(kb2) is True
m2 = db.match(kb2)
opener2 = next(r for r in db.roster(kb2) if r["slot"] == m2["holder"])
assert opener2["team"] != first_team, "kickoff alternates between consecutive matches"
assert engine.initial_lines(db.roster(kb2))[opener2["slot"]] == 2
print(f"ok  kickoff from the back; teams alternate (then {'red' if first_team == 1 else 'blue'} kicks off)")

db._conn.execute("DELETE FROM matches WHERE id IN (?,?)", (kb1, kb2))
db._conn.commit()
print("=" * 46)

# --- CATALOG: registry mirrored into ability_catalog -------------------------
from bluelock import abilities as _ab_mod
n_synced = _ab_mod.sync_catalog()
assert n_synced == len(_ab_mod.REGISTRY)
stats = dict(_ab_mod.catalog_stats())
assert sum(stats.values()) == len(_ab_mod.REGISTRY)
assert stats.get("gamble", 0) >= 6, "gamble skills must be categorized"
assert _ab_mod.category_of(_ab_mod.get("isagi_s1")) == "steal"
assert _ab_mod.category_of(_ab_mod.get("chigiri_s1")) == "rush"
assert _ab_mod.category_of(_ab_mod.get("karasu_s2")) == "penalty"
assert _ab_mod.category_of(_ab_mod.get("isagi_p2")) == "core", "first_free alone maps to core"
assert _ab_mod.category_of(_ab_mod.get("kaiser_s1")) == "draw"
print("ok  ability catalog synced:", dict(sorted(stats.items())))

fx_match = db.create_match(-555, "friendly", 2)
for uid, team in ((101, 1), (102, 1), (103, 2), (104, 2)):
    o = db.owned_by(uid)
    db.join_match(fx_match, team, uid, f"FX{uid}", o["char_key"],
                  characters.effective_stats(o["char_key"], json.loads(o["boosts"])))
assert engine.start(fx_match) is True
taker_fx = next(r for r in db.roster(fx_match) if r["user_id"] == 101)
mate_fx = next(r for r in db.roster(fx_match) if r["user_id"] == 102)

stage(fx_match, taker_fx["slot"], set_piece="freekick", zone=1)
opened = engine.open_duel(fx_match, "cross", mate_fx["slot"])
assert "error" not in opened
assert opened["defender"] is not None, "the cross is contested"
pending = engine.awaiting(db.match(fx_match))
assert pending["role"] == "att"
assert engine.submit_die(fx_match, 101, 6)["status"] == "ok"
while engine.awaiting(db.match(fx_match)):
    engine.record_die(fx_match, "def", 1)
out = engine.resolve(fx_match)
assert out["outcome"] == "cross_ok", out
after = engine.pending_of(db.match(fx_match))
assert after["zone"] == ZONE_SHOOT, "a landed cross arrives in the final third"
assert after["last_pass"] == taker_fx["slot"], "the cross sets up an assist chance"
assert db.match(fx_match)["holder"] == mate_fx["slot"]
print(engine.describe(out))
print("=" * 46)

assert db.find_player("@alpha")["user_id"] == 101
assert db.find_player("Alpha")["user_id"] == 101
assert db.find_player("nobody") is None

db.add_pending_yen("ghost", 500_000)
db.touch_player(998, "ghost")
assert db.player(998)["yen"] == 500_000

db.touch_player(997, "alpha")
assert db.player(101)["username"] is None
assert db.player(997)["username"] == "alpha"

race_match = db.create_match(-1, "friendly", 1)
outcomes = []
barrier = threading.Barrier(8)


def racer(uid):
    db.touch_player(uid, None)
    barrier.wait()
    outcomes.append(db.join_match(race_match, 1, uid, f"R{uid}", None, {}))


threads = [threading.Thread(target=racer, args=(2000 + i,)) for i in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()

assert outcomes.count("ok") == 1, outcomes
assert len(db.roster(race_match)) == 1

print("race outcomes:", sorted(outcomes))
print("\nCORE SIMULATION CHECKS PASSED")


# ==================================================================== #
#  ABILITY SUITE — manual skills (⚡ arm) + round-based passives        #
# ==================================================================== #

print("\n--- ABILITY SUITE ---")
random.seed(42)
config.ABILITIES_ENABLED = True

NEXT_UID = iter(range(3000, 4000))
CHAR_POOL = {}


def make_user(char_key: str, unlocks: list[str] | None = None) -> int:
    uid = next(NEXT_UID)
    db.touch_player(uid, None)
    db.assign_char(uid, char_key)
    for aid in unlocks or []:
        assert db.grant_unlock(uid, aid)
    CHAR_POOL[uid] = char_key
    return uid


def build_match(pairs: list[tuple[int, int]]) -> int:
    mid = db.create_match(-(100000 + next(NEXT_UID)), "friendly", len(pairs))
    for team, uids in ((1, [p[0] for p in pairs]), (2, [p[1] for p in pairs])):
        for uid in uids:
            o = db.owned_by(uid)
            db.join_match(
                mid, team, uid, f"T{team}{uid}", o["char_key"],
                characters.effective_stats(o["char_key"], {}),
            )
    assert engine.start(mid)
    return mid


def slot_of(mid: int, uid: int) -> int:
    return next(r["slot"] for r in db.roster(mid) if r["user_id"] == uid)


def do_arm(mid: int, slot: int, aid: str) -> None:
    st = engine.pending_of(db.match(mid))
    st.setdefault("armed", {})[str(slot)] = aid
    db.update_match(mid, pending=json.dumps(st))


def do_disarm(mid: int, slot: int) -> None:
    st = engine.pending_of(db.match(mid))
    st.get("armed", {}).pop(str(slot), None)
    db.update_match(mid, pending=json.dumps(st))


def roll_and_resolve(mid: int, att: int | None = None, dfn: int | None = None, gk: int | None = None):
    while True:
        pending = engine.awaiting(db.match(mid))
        if pending is None:
            break
        if pending["role"] == "gk":
            engine.record_die(mid, "gk", gk if gk is not None else 3)
        elif pending["role"] in ("spot", "spot_gk"):
            engine.submit_spot(mid, pending["user_id"], "left")
        else:
            val = att if pending["role"] == "att" else (dfn if dfn is not None else 1)
            assert engine.submit_die(mid, pending["user_id"], val)["status"] == "ok"
    return engine.resolve(mid)


# S1: Cold Predator + Bloodline Rivalry passives arm manually and stack while losing
rin_u = make_user("rin", unlocks=["rin_p2"])
isagi_u = make_user("isagi")
def_u = make_user("wanima_a")
def_u2 = make_user("tokimitsu")
mid = build_match([(rin_u, def_u), (isagi_u, def_u2)])
db.update_match(mid, score1=0, score2=1)
rs = slot_of(mid, rin_u)
base_dri = characters.base_stats("rin")["dribble"]


def arm_stage(m: int, slot: int, aid: str, **kw) -> None:
    prev = engine.pending_of(db.match(m))
    stage(m, slot, **kw)
    st = engine.pending_of(db.match(m))
    st["charges"] = prev.get("charges", {})
    st["used"] = prev.get("used", [])
    db.update_match(m, pending=json.dumps(st))
    do_arm(m, slot, aid)


def restage(m: int, slot: int, **kw) -> None:
    prev = engine.pending_of(db.match(m))
    stage(m, slot, **kw)
    st = engine.pending_of(db.match(m))
    st["charges"] = prev.get("charges", {})
    st["used"] = prev.get("used", [])
    db.update_match(m, pending=json.dumps(st))


restage(mid, rs, zone=0)
opened = engine.open_duel(mid, "dribble", None)
assert opened["duel"]["att_power"] == base_dri + 2, ("passive must arm itself", opened["duel"]["att_power"])
assert opened["duel"]["att_boosts"] == [("Cold Predator", 2)], opened["duel"]["att_boosts"]
engine.cancel_duel(mid)
st = engine.pending_of(db.match(mid))
assert st["charges"]["rin_p1"] == 1, "auto-fired passive used one of two charges"

restage(mid, rs, zone=0)
opened = engine.open_duel(mid, "dribble", None)
assert opened["duel"]["att_power"] == base_dri + 2, "second charge fires on its own too"
engine.cancel_duel(mid)
st = engine.pending_of(db.match(mid))
assert "rin_p1" in st["used"], "second use exhausts the passive"

restage(mid, rs, zone=0)
opened = engine.open_duel(mid, "dribble", None)
assert ("Cold Predator", 2) not in opened["duel"]["att_boosts"], "spent passive must not fire again"
engine.cancel_duel(mid)
assert engine.arm_skill(mid, rin_u, "rin_p1")["status"] == "spent"
print("ok  passives fire on their own: 2 charges, boosts tagged on the calc line")

# S2: passive condition checked at resolution, not blindly.
# last_pass holds the PASSER's slot, so stage a real received pass from the teammate.
isagi_slot = slot_of(mid, isagi_u)
mate_isagi = next(r["slot"] for r in db.roster(mid) if r["team"] == 1 and r["slot"] != isagi_slot)
base_sho = characters.base_stats("isagi")["shot"]
arm_stage(mid, isagi_slot, "isagi_p1", zone=ZONE_SHOOT, last_pass=None)
opened = engine.open_duel(mid, "shoot", None)
assert opened["duel"]["att_power"] == base_sho, "condition not met — no boost, charge stays"
engine.cancel_duel(mid)
st = engine.pending_of(db.match(mid))
assert "isagi_p1" not in st.get("used", []), "armed but unspent condition must stay charged"
stage(mid, isagi_slot, zone=ZONE_SHOOT, last_pass=mate_isagi)
do_arm(mid, isagi_slot, "isagi_p1")
opened = engine.open_duel(mid, "shoot", None)
assert opened["duel"]["att_power"] == base_sho + 2
assert opened["duel"]["att_boosts"] == [("Direct Hit", 2)]
engine.cancel_duel(mid)
stage(mid, isagi_slot, zone=ZONE_SHOOT, last_pass=None)
do_arm(mid, isagi_slot, "isagi_p1")
opened = engine.open_duel(mid, "shoot", None)
assert opened["duel"]["att_power"] == base_sho, "holding the ball without a fresh pass must NOT count"
engine.cancel_duel(mid)
print("ok  Direct Hit fires only on a real received pass (passer slot != shooter)")

# S3: Impossible Trap must be ARMED; then auto-wins once and is spent
nagi_u = make_user("nagi")
mid2 = build_match([(nagi_u, def_u)])
ns = slot_of(mid2, nagi_u)
stage(mid2, ns, zone=0)
opened = engine.open_duel(mid2, "dribble", None)
assert opened["duel"].get("auto") is None, "un-armed skill must stay idle"
assert engine.awaiting(db.match(mid2))["role"] == "att"
engine.cancel_duel(mid2)

do_arm(mid2, ns, "nagi_s1")
m2 = db.match(mid2)
assert db.claim_turn(mid2, m2["turn"], ns)
opened = engine.open_duel(mid2, "dribble", None)
assert isinstance(opened["duel"].get("auto"), dict) and opened["duel"]["auto"]["t"] == "win"
assert any("Impossible Trap" in n for n in opened.get("notes", []))
assert engine.awaiting(db.match(mid2)) is None, "armed auto-win needs no dice"
out = roll_and_resolve(mid2)
assert out["outcome"] == "dribble_ok"
pend = engine.pending_of(db.match(mid2))
assert "nagi_s1" in pend["used"] and not pend.get("armed")

m2 = db.match(mid2)
assert db.claim_turn(mid2, m2["turn"], ns)
opened = engine.open_duel(mid2, "dribble", None)
assert opened["duel"].get("auto") is None, "charge spent — no second trigger"
engine.cancel_duel(mid2)
print("ok  nagi skill armed -> fired once -> spent")

# S4: Emperor's Draw armed, then converts a lost duel into a set piece
kaiser_u = make_user("kaiser")
mid3 = build_match([(kaiser_u, def_u)])
ks = slot_of(mid3, kaiser_u)
stage(mid3, ks, zone=ZONE_SHOOT)
do_arm(mid3, ks, "kaiser_s1")
opened = engine.open_duel(mid3, "shoot", None)
out = roll_and_resolve(mid3, att=1, dfn=6, gk=6)
assert out["outcome"] == "foul" and out["reason"] == "drawn"
piece = engine.pending_of(db.match(mid3))["set_piece"]
assert piece == "freekick"
print("ok  kaiser foul draw armed ->", piece)

# S5: Silent Service passive armed; buff lands and receiver spends it next action
hiori_u = make_user("hiori")
mid4 = build_match([(hiori_u, def_u), (kaiser_u, def_u2)])
hs = slot_of(mid4, hiori_u)
ks4 = slot_of(mid4, kaiser_u)
arm_stage(mid4, hs, "hiori_p1", zone=0)
engine.open_duel(mid4, "pass", ks4)
out = roll_and_resolve(mid4, att=6, dfn=1)
assert out["outcome"] == "pass_ok"
buffs = engine.pending_of(db.match(mid4))["buffs"]
assert buffs and buffs[0]["slot"] == ks4 and buffs[0]["amt"] == 1
m4 = db.match(mid4)
assert db.claim_turn(mid4, m4["turn"], ks4)
opened = engine.open_duel(mid4, "dribble", None)
kaiser_dri = characters.base_stats("kaiser")["dribble"]
assert opened["duel"]["att_power"] == kaiser_dri + 1, "buff rides on receiver's action"
engine.cancel_duel(mid4)
print("ok  hiori pass buff grant + consumption")

# S6: Devil's Pulse armed — keeper cut down on the compare line
shidou_u = make_user("shidou", unlocks=["shidou_s2"])
mid5 = build_match([(shidou_u, def_u)])
ss = slot_of(mid5, shidou_u)
stage(mid5, ss, zone=ZONE_SHOOT)
do_arm(mid5, ss, "shidou_s2")
engine.open_duel(mid5, "shoot", None)
out = roll_and_resolve(mid5, att=6, dfn=1, gk=6)
assert out["gk_total_eff"] == out["gk_total"] - 2, (out.get("gk_total_eff"), out["gk_total"])
assert any("Devil's Pulse" in n for n in out.get("notes", []))
print("ok  shidou gk_down:", out["gk_total"], "->", out["gk_total_eff"])

# S7: Direct free kick faces the keeper alone (wall removed)
rin2 = rin_u
mid6 = build_match([(rin2, def_u)])
rs6 = slot_of(mid6, rin2)
stage(mid6, rs6, zone=ZONE_SHOOT, set_piece="freekick")
opened = engine.open_duel(mid6, "freekick", None)
assert opened["duel"]["defender"] is None
assert opened["duel"]["gk_power"] == KEEPER_POWER, "no wall bonus"
assert opened["duel"].get("wall") == [], "direct set pieces face no field wall"
engine.cancel_duel(mid6)
print("ok  direct free kick: keeper only, no wall")

# S8: Cross delivery lands with assist credit lined up
chigiri_u = make_user("chigiri")
mid7 = build_match([(chigiri_u, def_u), (nagi_u, def_u2)])
cs = slot_of(mid7, chigiri_u)
ns7 = slot_of(mid7, nagi_u)
stage(mid7, cs, zone=ZONE_SHOOT, set_piece="freekick")
opened = engine.open_duel(mid7, "cross", ns7)
assert opened["duel"]["defender"] is not None
out = roll_and_resolve(mid7, att=6, dfn=1)
assert out["outcome"] == "cross_ok"
after = engine.pending_of(db.match(mid7))
assert after["zone"] == ZONE_SHOOT and after["last_pass"] == cs
assert db.match(mid7)["holder"] == ns7
print("ok  cross delivery + assist setup")

# S9: Checkmate Call armed on a penalty sends the keeper the wrong way
karasu_u = make_user("karasu", unlocks=["karasu_s2"])
mid8 = build_match([(karasu_u, def_u)])
kslot = slot_of(mid8, karasu_u)
stage(mid8, kslot, zone=ZONE_BOX, set_piece="penalty")
do_arm(mid8, kslot, "karasu_s2")
engine.open_duel(mid8, "penalty", None)
engine.submit_spot(mid8, karasu_u, "center")
engine.submit_spot(mid8, def_u, "center")
out = engine.resolve(mid8)
assert out["outcome"] == "goal" and out.get("autoscore")
assert out["gk_spot"] != "center"
assert "karasu_s2" in engine.pending_of(db.match(mid8))["used"]
print("ok  karasu penalty autoscore (armed)")

# S10: Tryhard Heart die floor (armed passive) both directions
iga_u = make_user("igaguri")
mid9 = build_match([(iga_u, def_u)])
gs = slot_of(mid9, iga_u)
arm_stage(mid9, gs, "igaguri_p1", zone=0)
opened = engine.open_duel(mid9, "dribble", None)
assert engine.submit_die(mid9, iga_u, 1)["status"] == "ok"
duel = engine.pending_of(db.match(mid9))["duel"]
assert duel["att_floor"] == 2
assert engine.total(duel, "att") == 2 + characters.base_stats("igaguri")["dribble"]
engine.cancel_duel(mid9)

clean_att = make_user("wanima_j")
mid10 = build_match([(clean_att, iga_u)])
cas = slot_of(mid10, clean_att)
stage(mid10, cas, zone=0)
engine.open_duel(mid10, "dribble", None)
assert engine.submit_die(mid10, clean_att, 6)["status"] == "ok"
assert engine.record_die(mid10, "def", 1) is True
duel = engine.pending_of(db.match(mid10))["duel"]
assert duel["def_floor"] == 2, "passive die floor must arm itself"
engine.cancel_duel(mid10)
print("ok  die floor arms itself on both sides")

# S11: economy gating — tiers, prices, innate starters, idempotent grants
cost2, lv2 = abilities.price_and_level(abilities.get("rin_p2"))
cost3, lv3 = abilities.price_and_level(abilities.get("rin_s2"))
cost4, lv4 = abilities.price_and_level(abilities.get("isagi_s3"))
assert (lv2, lv3, lv4) == (
    config.ABILITY_T2_LEVEL, config.ABILITY_T3_LEVEL, config.ABILITY_T4_LEVEL
)
assert cost2 < cost3 < cost4
assert len(abilities.kit_for_char("isagi")) == 6
fresh = make_user("sae")
starters = abilities.starter_ids("sae")
assert abilities.owned_ids(fresh, "sae") == starters
assert db.grant_unlock(fresh, "sae_p2") is True
assert db.grant_unlock(fresh, "sae_p2") is False
text, kb = views.kit_page(fresh, "sae")
assert "World-Class Weight" in text and "Possession Metronome" in text
assert "button" in text.lower() or "\u26a1" in text
print("ok  unlock economy + kit page renders")

# S11b: ULTIMATE armed — Devour the Match saves-be-damned margin goal
assert db.grant_unlock(isagi_u, "isagi_s3")
midU = build_match([(isagi_u, def_u)])
us = slot_of(midU, isagi_u)
stage(midU, us, zone=ZONE_SHOOT)
do_arm(midU, us, "isagi_s3")
engine.open_duel(midU, "shoot", None)
out = roll_and_resolve(midU, att=4, dfn=1, gk=6)
assert out["outcome"] == "goal" and out.get("margin_goal") == 2
assert "isagi_s3" in engine.pending_of(db.match(midU))["used"]
print("ok  isagi ultimate margin goal (armed)")

# S11c: arm -> disarm refunds without spending; re-arm works
kaiser_uid = [u for u in CHAR_POOL if CHAR_POOL[u] == "kaiser"][-1]
j_uid = [u for u in CHAR_POOL if CHAR_POOL[u] == "wanima_j"][-1]
assert db.grant_unlock(kaiser_uid, "kaiser_s2")
midV = build_match([(kaiser_uid, j_uid)])
kv = slot_of(midV, kaiser_uid)
stage(midV, kv, zone=ZONE_SHOOT)
do_arm(midV, kv, "kaiser_s2")
st_v = engine.pending_of(db.match(midV))
assert st_v["armed"][str(kv)] == "kaiser_s2"
do_disarm(midV, kv)
st_v = engine.pending_of(db.match(midV))
assert not st_v.get("armed") and "kaiser_s2" not in st_v["used"], "disarm refunds"
opened_v = engine.open_duel(midV, "shoot", None)
assert opened_v["duel"]["gk_power"] >= KEEPER_POWER
engine.cancel_duel(midV)
stage(midV, kv, zone=ZONE_SHOOT)
do_arm(midV, kv, "kaiser_s2")
engine.open_duel(midV, "shoot", None)
out = roll_and_resolve(midV, att=4, dfn=1, gk=6)
assert out.get("margin_goal") == 1, out
print("ok  arm/disarm lifecycle + Der Übermensch margin")

# S12: DEFENSIVE arming — defender stops an attacker's dribble cold
otoya_u = make_user("otoya")
presser_u = make_user("kurona", unlocks=["kurona_s2"])
target_u = make_user("wanima_a") if False else def_u
midW = build_match([(presser_u, otoya_u)])
pslot = slot_of(midW, presser_u)
oslot = slot_of(midW, otoya_u)
stage(midW, pslot, zone=0)
do_arm(midW, oslot, "kurona_s2")
opened = engine.open_duel(midW, "dribble", None)
assert isinstance(opened["duel"].get("auto"), dict) and opened["duel"]["auto"]["t"] == "stop"
assert opened["duel"]["auto"]["slot"] == oslot
assert engine.awaiting(db.match(midW)) is None
out = roll_and_resolve(midW)
assert out["outcome"] == "tackled" and out["stopped_by_skill"]["slot"] == oslot
assert "kurona_s2" in engine.pending_of(db.match(midW))["used"]
print("ok  defensive arm: kurona piranha press")

# S12b: Devour the Stage — first lost duel doesn't count, turn returns to the actor
devour_u = isagi_u
assert db.grant_unlock(devour_u, "isagi_p2")
midY = build_match([(devour_u, def_u)])
yslot = slot_of(midY, devour_u)
dslotY = slot_of(midY, def_u)
stage(midY, yslot, zone=0)
do_arm(midY, yslot, "isagi_p2")
opened = engine.open_duel(midY, "dribble", None)
assert not opened["duel"].get("no_dice")
out = roll_and_resolve(midY, att=1, dfn=6)
assert out["outcome"] in ("tackled", "blocked") and out.get("first_free") is True, (out["outcome"], out.get("first_free"))
afterY = db.match(midY)
assert afterY["phase"] == "play", "devour replays the turn"
assert afterY["holder"] == yslot, "ball stays with the devourer"
assert afterY["turn"] == 1, f"turn should NOT advance on devour, got {afterY['turn']}"
pendingY = engine.pending_of(afterY)
assert pendingY["charges"].get("isagi_p2") == 1, "devour burns one of two charges"
assert not pendingY.get("duel")
assert engine.describe(out).count("doesn't count") == 1
print("ok  devour the stage: first loss replays the turn, charge spent")

# second loss is real — no charge left
stage(midY, yslot, zone=0)
opened = engine.open_duel(midY, "dribble", None)
out = roll_and_resolve(midY, att=1, dfn=6)
assert out["outcome"] in ("tackled", "blocked") and not out.get("first_free"), "no second devour"
assert db.match(midY)["holder"] == dslotY, "second loss is a real turnover"
print("ok  devour the stage: only the first loss is free")

# S12b: canon newcomers — kits of six render, and one duel proves they play
new_users = {}
for nk in ("aiku", "charles", "ness", "zantetsu"):
    assert characters.resolve(characters.name_of(nk)) == nk, nk
    assert len(abilities.kit_for_char(nk)) == 6, nk
    n_u = make_user(nk)
    new_users[nk] = n_u
    n_txt, _ = views.kit_page(n_u, nk)
    assert abilities.kit_for_char(nk)[0].name in n_txt, nk
print("ok  newcomers: Aiku/Charles/Ness/Zantetsu kits of six render")

z_u = new_users["zantetsu"]
a_u = new_users["aiku"]
mZ = build_match([(z_u, a_u)])
zs = slot_of(mZ, z_u)
stage(mZ, zs, zone=1)
do_arm(mZ, zs, "zantetsu_s1")
opened = engine.open_duel(mZ, "dribble", None)
assert opened["duel"].get("auto", {}).get("t") == "win", "Steel Dash must win outright"
assert any(nm == "Board Vision" for nm, _ in opened["duel"]["def_boosts"]), opened["duel"]["def_boosts"]
out = roll_and_resolve(mZ, att=1, dfn=6)
assert out["outcome"] == "dribble_ok"
assert engine.pending_of(db.match(mZ))["zone"] > 1, "a dribble win advances the zone"
print("ok  newcomers duel: Steel Dash auto-wins + zone, Board Vision defends")

# S13: full simulated ranked match WITH abilities stays coherent
sim_u3 = make_user("bachira")
sim_u4 = make_user("kunigami", unlocks=["kunigami_s2"])
midX = build_match([(isagi_u, sim_u3), (rin_u, sim_u4)])
db.update_match(midX, mode="ranked")
random.seed(7)
steps = 0
while not engine.over(db.match(midX)):
    steps += 1
    assert steps < 300
    m = db.match(midX)
    state = engine.pending_of(m)
    piece = state.get("set_piece")
    zone = state.get("zone", 0)
    holder = next(r for r in db.roster(midX) if r["slot"] == m["holder"])
    kit_skills = [
        abilities.get(a) for a in abilities.owned_ids(holder["user_id"], holder["char_key"])
        if abilities.get(a) and abilities.get(a).kind == "skill"
        and abilities.get(a).id not in state.get("used", [])
    ]
    if kit_skills and random.random() < 0.35:
        pick = random.choice(kit_skills)
        do_arm(midX, holder["slot"], pick.id)
        state = engine.pending_of(db.match(midX))
    if piece == "penalty":
        action, target = "penalty", None
    elif piece == "freekick":
        action, target = random.choice(["freekick", "cross"]), None
    elif zone >= ZONE_SHOOT and random.random() < 0.6:
        action, target = "shoot", None
    elif zone < ZONE_BOX and random.random() < 0.5:
        action, target = "dribble", None
    else:
        mates = [r for r in db.roster(midX) if r["team"] == holder["team"] and r["slot"] != holder["slot"]]
        action, target = ("pass", random.choice(mates)["slot"]) if mates else ("shoot", None)
    assert db.claim_turn(midX, m["turn"], holder["slot"])
    opened = engine.open_duel(midX, action, target)
    if "error" in opened:
        db.release_turn(midX)
        continue
    while True:
        pending = engine.awaiting(db.match(midX))
        if pending is None:
            break
        if pending["role"] == "gk":
            engine.record_die(midX, "gk", random.randint(1, 6))
        elif pending["role"] in ("spot", "spot_gk"):
            engine.submit_spot(midX, pending["user_id"], random.choice(config.PENALTY_TARGETS))
        else:
            engine.submit_die(midX, pending["user_id"], random.randint(1, 6))
    out = engine.resolve(midX)
    assert out is not None
    desc = engine.describe(out, {r["slot"]: r for r in db.roster(midX)})
    assert desc.strip()
finalX = db.match(midX)
print(f"ok  ability-mode ranked sim finished {finalX['score1']}-{finalX['score2']} in {steps} actions")
rep, lus = payouts.settle(midX)
assert rep and "MAN OF THE MATCH" in rep
print(rep.splitlines()[0])

# --- tie_win: a pure tie-win pass skill beats the exact-tie deadlock --------
tw_u = 104
tw_m = rin_u
midTW = build_match([(tw_u, def_u2), (tw_m, def_u)])
stage(midTW, slot_of(midTW, tw_u), zone=1)
do_arm(midTW, slot_of(midTW, tw_u), "hyoma_k_s2")
opened = engine.open_duel(midTW, "pass", slot_of(midTW, tw_m))
assert opened["duel"].get("tie_win") is True, "pure tie_win skill must arm at open"
assert "hyoma_k_s2" in engine.pending_of(db.match(midTW)).get("used", []), "tie_win skill spends at open"
ap, dp = opened["duel"]["att_power"], opened["duel"]["def_power"]
tie_att = next(d for d in range(1, DICE_FACES + 1) if 1 <= d + ap - dp <= DICE_FACES)
tie_def = tie_att + ap - dp
out = roll_and_resolve(midTW, att=tie_att, dfn=tie_def)
assert out["outcome"] == "pass_ok", f"tie_win must complete the pass on an exact tie, got {out['outcome']}"
print("ok  tie_win pass skill: exact tie completes the pass instead of a set piece")

# same exact tie without tie_win is still a deadlock set piece
midCTL = build_match([(101, 102), (isagi_u, shidou_u)])
stage(midCTL, slot_of(midCTL, 101), zone=1)
opened = engine.open_duel(midCTL, "pass", slot_of(midCTL, isagi_u))
ap, dp = opened["duel"]["att_power"], opened["duel"]["def_power"]
tie_att = next(d for d in range(1, DICE_FACES + 1) if 1 <= d + ap - dp <= DICE_FACES)
tie_def = tie_att + ap - dp
out = roll_and_resolve(midCTL, att=tie_att, dfn=tie_def)
assert out["outcome"] == "foul" and out["reason"] == "deadlock", "plain exact tie must stay a set piece"
assert out["att_total"] == out["def_total"]
print("ok  exact tie without tie_win still awards the deadlock set piece")

# --- pass_advance: the delivery is uninterceptable and the charge is spent --
midPA = build_match([(hiori_u, def_u), (isagi_u, nagi_u)])
stage(midPA, slot_of(midPA, hiori_u), zone=0)
do_arm(midPA, slot_of(midPA, hiori_u), "hiori_s1")
opened = engine.open_duel(midPA, "pass", slot_of(midPA, isagi_u))
assert opened["duel"].get("ghost_pass") is True, "pass_advance pass must be flagged uninterceptable"
out = roll_and_resolve(midPA, att=1)
assert out["outcome"] == "pass_ok", "even the worst roll must complete an uninterceptable pass"
assert out["def_die"] is None, "the interceptor never rolls"
pend = engine.pending_of(db.match(midPA))
assert "hiori_s1" in pend.get("used", []), "pass_advance must spend its charge on the completed pass"
assert pend["zone"] == min(ZONE_BOX, 0 + 1 + 1), (pend["zone"], "normal +1 pass advance plus the skill's +1")
desc = engine.describe(out, {r["slot"]: r for r in db.roster(midPA)})
assert "None+" not in desc, desc
print("ok  pass_advance: uninterceptable, +zone, charge spent, clean render")

# unmarked pass with pass_advance also spends (no infinite zone jumps)
midUM = build_match([(fresh, iga_u), (chigiri_u, karasu_u)])
foe_a = slot_of(midUM, iga_u)
foe_b = slot_of(midUM, karasu_u)
stage(midUM, slot_of(midUM, fresh), zone=0, beaten=[foe_a, foe_b])
do_arm(midUM, slot_of(midUM, fresh), "sae_s3")
opened = engine.open_duel(midUM, "pass", slot_of(midUM, chigiri_u))
assert opened["duel"].get("no_dice") is True, "both markers beaten means a dice-free walk"
out = roll_and_resolve(midUM)
assert out["outcome"] == "pass_ok" and out.get("walked") is True
pend = engine.pending_of(db.match(midUM))
assert "sae_s3" in pend.get("used", []), "unmarked delivery must still spend pass_advance"
assert pend["zone"] == min(ZONE_BOX, 0 + 1 + 2), pend["zone"]
print("ok  unmarked pass_advance: charge spent, +2 zones applied once")

config.ABILITIES_ENABLED = False

print("\nABILITY SUITE PASSED")
print("\nALL SIMULATION CHECKS PASSED")
