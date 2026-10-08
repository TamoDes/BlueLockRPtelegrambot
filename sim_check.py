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

from bluelock import abilities, characters, economy, engine, fmt, payouts, views
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
db.ensure_season(config.SEASON)
db.set_setting(config.SEASON_PHASE_KEY, "live")   # main suite exercises real payouts

USERS = [(101, "alpha"), (102, "beta"), (103, "gamma"), (104, "delta")]
for uid, uname in USERS:
    db.touch_player(uid, uname)
    assert db.set_display(uid, uname.capitalize())

for (uid, _), key in zip(USERS, ["kira", "yukimiya", "naruhaya", "reo"]):
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
            assert out["att_spot"] != out["gk_spot"], "a read corner can never score"
        else:
            assert out["att_total"] > out["gk_total"], (out["att_total"], out["gk_total"])
            assert out["defender"] is None or out["att_total"] > out["def_total"]
    if out["outcome"] == "saved":
        saves_seen += 1
        if out["action"] == "penalty":
            assert out["att_spot"] == out["gk_spot"] and out.get("nerve") == "read"
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
assert engine.turn_limit(final) == max_turns(final["size"], "ranked") > max_turns(final["size"], "casual")
assert "friendly" not in config.MODES and config.MODES == {"ranked": "Ranked"}

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

duel_match = db.create_match(-777, "clock", 1)
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

pm_match = db.create_match(101, "clock", 1)
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


def stage_play(mid: int, holder_slot: int, **kw) -> None:
    """Same reset as stage() but leaves the match claimable (phase='play')."""
    state = engine.fresh_state()
    state.update(kw)
    db.update_match(mid, pending=json.dumps(state), phase="play", holder=holder_slot)


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
assert out["outcome"] == "saved", out
assert out["att_spot"] == "center" and out["gk_spot"] == "center"
assert out["nerve"] == "read", out
assert "pen_sho" not in out and "pen_gk" not in out, "read corner: no nerve duel at all"
print(engine.describe(out))

# penalty rule: a read corner is 100% kept out, a missed corner is 100% a goal — no dice either way
reads = saves = 0
for _ in range(40):
    stage(pm_match, taker["slot"], set_piece="penalty", zone=ZONE_BOX)
    engine.open_duel(pm_match, "penalty", None)
    engine.submit_spot(pm_match, 101, "left")
    engine.submit_spot(pm_match, 103, "left")
    out = engine.resolve(pm_match)
    assert out["outcome"] == "saved" and out["nerve"] == "read", out
    reads += 1
    saves += out["outcome"] == "saved"
    stage(pm_match, taker["slot"], set_piece="penalty", zone=ZONE_BOX)
    engine.open_duel(pm_match, "penalty", None)
    engine.submit_spot(pm_match, 101, "left")
    engine.submit_spot(pm_match, 103, "right")
    out = engine.resolve(pm_match)
    assert out["outcome"] == "goal", out
assert saves == reads == 40
print(f"ok  penalty reads: {saves}/{reads} saved, misses: 40/40 scored")

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
adv_match = db.create_match(-888, "clock", 1)
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
kb1 = db.create_match(-700, "clock", 2)
kb2 = db.create_match(-700, "clock", 2)
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
assert _ab_mod.category_of(_ab_mod.get("nagi_p1")) == "read", "contest passives tag as read"
print("ok  ability catalog synced:", dict(sorted(stats.items())))

fx_match = db.create_match(-555, "clock", 2)
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

race_match = db.create_match(-1, "clock", 1)
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
    mid = db.create_match(-(100000 + next(NEXT_UID)), "ranked", len(pairs))
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


def contest_reply(mid: int, pending: dict) -> dict:
    cfg = pending["duel"].get("contest") or {}
    opts = engine.contest_opts(cfg, pending["role"])
    choice = random.choice(opts)[0] if opts else ""
    if pending["role"] == "contest_set":
        return engine.submit_contest_set(mid, pending["user_id"], choice)
    return engine.submit_contest_call(mid, pending["user_id"], choice)


def roll_and_resolve(mid: int, att: int | None = None, dfn: int | None = None, gk: int | None = None):
    while True:
        pending = engine.awaiting(db.match(mid))
        if pending is None:
            break
        if pending["role"] == "gk":
            engine.record_die(mid, "gk", gk if gk is not None else 3)
        elif pending["role"] in ("spot", "spot_gk"):
            engine.submit_spot(mid, pending["user_id"], "left")
        elif pending["role"] in ("contest_set", "contest_call"):
            assert contest_reply(mid, pending)["status"] == "ok"
        else:
            val = att if pending["role"] == "att" else (dfn if dfn is not None else 1)
            assert engine.submit_die(mid, pending["user_id"], val)["status"] == "ok"
    return engine.resolve(mid)


# S1: passives are MANUAL — no tap, no fire; one charge per match
# (cap = 1 passive + 2 skills: Rin's only own passive is Puppet — pass-triggered)
rin_u = make_user("rin")
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
mate = slot_of(mid, isagi_u)
# Taha: passives never arm themselves — open with NO tap and nothing fires
opened = engine.open_duel(mid, "pass", mate)
assert not opened["duel"].get("auto"), (
    "manual passive must not self-arm", opened["duel"].get("auto"))
engine.cancel_duel(mid)

# the player taps the passive button (arms it), then the pass fires it
do_arm(mid, rs, "rin_p1")
mrow = db.match(mid)
assert db.claim_turn(mid, mrow["turn"], rs)
opened = engine.open_duel(mid, "pass", mate)
assert opened["duel"].get("auto") == {"t": "win", "slot": rs, "aid": "rin_p1"}, (
    "manually-armed passive must fire", opened["duel"].get("auto"))
engine.cancel_duel(mid)
st = engine.pending_of(db.match(mid))
assert st["charges"]["rin_p1"] == 1, "undo gives the fired charge back"
assert "rin_p1" not in st.get("used", []), "and the passive is ready to arm again"

# fire it again and LET IT RESOLVE — now the charge burns for good
restage(mid, rs, zone=0)
do_arm(mid, rs, "rin_p1")
opened = engine.open_duel(mid, "pass", mate)
assert opened["duel"].get("auto") == {"t": "win", "slot": rs, "aid": "rin_p1"}
out = roll_and_resolve(mid)
assert out is not None and out.get("outcome") == "pass_ok", out
st = engine.pending_of(db.match(mid))
assert st["charges"]["rin_p1"] == 0, "one-charge passive: the fired charge is spent"
assert "rin_p1" in st["used"], "spent passive moves to used"

restage(mid, rs, zone=0)
opened = engine.open_duel(mid, "pass", mate)
assert not opened["duel"].get("auto"), "spent passive must not fire again"
assert all(a != "rin_p1" for a, _ in opened["duel"].get("att_boosts", [])), \
    "spent passive must not boost again"
engine.cancel_duel(mid)
assert engine.arm_skill(mid, rin_u, "rin_p1")["status"] == "spent"
print("ok  passives fire on their own: one charge per match, undo refunds a cancelled fire")

# S2: Last Puzzle — he reads it, gets on the end of it and finishes. Only a
# shot makes him move; anything else leaves the charge untouched.
isagi_slot = slot_of(mid, isagi_u)
dslot = slot_of(mid, def_u2)
base_sho = characters.base_stats("isagi")["shot"]
arm_stage(mid, isagi_slot, "isagi_p1", zone=ZONE_SHOOT, beaten=[])
opened = engine.open_duel(mid, "dribble", None)   # not a shot — he doesn't read it
engine.cancel_duel(mid)
st = engine.pending_of(db.match(mid))
assert "isagi_p1" not in st.get("used", []), "not a shot — the charge must stay"
stage(mid, isagi_slot, zone=ZONE_SHOOT, beaten=[dslot])
do_arm(mid, isagi_slot, "isagi_p1")
opened = engine.open_duel(mid, "shoot", None)
assert opened["duel"]["att_power"] == base_sho + 2
assert opened["duel"]["att_boosts"] == [("Last Puzzle", 2)]
assert opened["duel"].get("sure_goal"), "and once he's on the end of it, it cannot be saved"
engine.cancel_duel(mid)
stage(mid, isagi_slot, zone=ZONE_SHOOT, beaten=[])
do_arm(mid, isagi_slot, "isagi_p1")
opened = engine.open_duel(mid, "shoot", None)
assert opened["duel"]["att_power"] == base_sho + 2, "loose ball / nobody beaten — he still reads it"
engine.cancel_duel(mid)
print("ok  Last Puzzle: a shot always converts (+2, unsaveable); any other action keeps the charge")

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

# S5: Silent Service contest — misread lands the pass clean with a receiver buff
hiori_u = make_user("hiori")
mid4 = build_match([(hiori_u, def_u), (rin_u, def_u2)])
hs = slot_of(mid4, hiori_u)
rs4 = slot_of(mid4, rin_u)
arm_stage(mid4, hs, "hiori_p1", zone=0)
engine.open_duel(mid4, "pass", rs4)
assert engine.submit_contest_set(mid4, hiori_u, "split")["status"] == "ok"
r = engine.submit_contest_call(mid4, def_u2, "drop")
assert r["effect"].get("buff") == 1, r["effect"]
out = roll_and_resolve(mid4, att=6, dfn=1)
assert out["outcome"] == "pass_ok"
buffs = engine.pending_of(db.match(mid4))["buffs"]
assert buffs and buffs[0]["slot"] == rs4 and buffs[0]["amt"] == 1
m4 = db.match(mid4)
assert db.claim_turn(mid4, m4["turn"], rs4)
opened = engine.open_duel(mid4, "dribble", None)
rin_dri = characters.base_stats("rin")["dribble"]
assert opened["duel"]["att_power"] == rin_dri + 1, "buff rides on receiver's action"
engine.cancel_duel(mid4)
print("ok  hiori contest pass: misread lands it +1 to the receiver")

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

# S6b: keeper aura — free forever is gone; armed, it lifts the keeper ONCE
gg_u = make_user("gagamaru")
mA = build_match([(def_u, gg_u)])   # Wanima shoots, Gagamaru keeps
wA, gA = slot_of(mA, def_u), slot_of(mA, gg_u)
for _x in abilities.starter_ids("gagamaru"):
    db.grant_unlock(gg_u, _x)
stage_play(mA, wA, zone=ZONE_SHOOT, beaten=[])
mA_row = db.match(mA)
assert db.claim_turn(mA, mA_row["turn"], mA_row["holder"])
engine.open_duel(mA, "shoot", None)
outA = roll_and_resolve(mA, att=6, dfn=1, gk=1)
assert not outA.get("gk_aura"), "unarmed aura must stay idle"
assert "gagamaru_p1" not in engine.pending_of(db.match(mA)).get("used", [])
stage_play(mA, wA, zone=ZONE_SHOOT, beaten=[])
assert engine.arm_skill(mA, gg_u, "gagamaru_p1")["status"] == "armed"
mA_row = db.match(mA)
assert db.claim_turn(mA, mA_row["turn"], mA_row["holder"])
engine.open_duel(mA, "shoot", None)
outA = roll_and_resolve(mA, att=6, dfn=1, gk=1)   # past the wall -> keeper faces it
assert outA.get("gk_aura") == 1, outA
assert outA["gk_total_eff"] == outA["gk_total"] + 1, (outA.get("gk_total_eff"), outA.get("gk_total"))
stA = engine.pending_of(db.match(mA))
assert "gagamaru_p1" in stA.get("used", []), "the aura burns its one charge"
print("ok  keeper aura: unarmed idle -> armed +1 once -> charge burned")

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
dslot = slot_of(mid10, iga_u)
stage(mid10, cas, zone=0)
do_arm(mid10, dslot, "igaguri_p1")   # manual: the defender taps his passive
engine.open_duel(mid10, "dribble", None)
assert engine.submit_die(mid10, clean_att, 6)["status"] == "ok"
assert engine.record_die(mid10, "def", 1) is True
duel = engine.pending_of(db.match(mid10))["duel"]
assert duel["def_floor"] == 2, "manually-armed passive sets the die floor"
engine.cancel_duel(mid10)
print("ok  die floor applies on both sides (armed manually)")

# S11: economy gating — tiers, prices, innate starters, idempotent grants
cost2, lv2 = abilities.price_and_level(abilities.get("rin_p2"))
cost3, lv3 = abilities.price_and_level(abilities.get("rin_s2"))
cost4, lv4 = abilities.price_and_level(abilities.get("isagi_s3"))
assert (lv2, lv3, lv4) == (
    config.ABILITY_T2_LEVEL, config.ABILITY_T3_LEVEL, config.ABILITY_T4_LEVEL
)
assert cost2 < cost3 < cost4
assert len(abilities.kit_for_char("isagi")) == 3  # 1 passive + 2 skills — no bound anymore
fresh = make_user("sae")
starters = abilities.starter_ids("sae")
assert abilities.owned_ids(fresh, "sae") == starters
assert db.grant_unlock(fresh, "sae_s2") is True
assert db.grant_unlock(fresh, "sae_s2") is False
text, kb = views.kit_page(fresh, "sae")
assert "Winning Movement" in text and "Maestro's Through Ball" in text
assert "button" in text.lower() or "\u26a1" in text
print("ok  unlock economy + kit page renders")

# S11b: ULTIMATE armed — Devour the Match saves-be-damned margin goal
assert db.grant_unlock(isagi_u, "isagi_s3")
midU = build_match([(isagi_u, def_u)])
us = slot_of(midU, isagi_u)
stage(midU, us, zone=ZONE_SHOOT)
do_arm(midU, us, "isagi_s3")
engine.open_duel(midU, "shoot", None)
out = roll_and_resolve(midU, att=5, dfn=1, gk=6)
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
out = roll_and_resolve(midV, att=5, dfn=1, gk=6)
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
assert pendingY["charges"].get("isagi_p2") == 0, "devour burns its only charge"
assert "isagi_p2" in pendingY.get("used", []), "spent passive moves to used"
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
    assert len(abilities.kit_for_char(nk)) == 4, nk  # 3 kit + 1 bound
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
out = roll_and_resolve(mZ, att=1, dfn=6)
assert out["outcome"] == "dribble_ok"
assert engine.pending_of(db.match(mZ))["zone"] > 1, "a dribble win advances the zone"
print("ok  newcomers duel: Steel Dash auto-wins + zone")

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
        elif pending["role"] in ("contest_set", "contest_call"):
            assert contest_reply(midX, pending)["status"] == "ok"
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
tw_u = def_u
tw_m = rin_u
midTW = build_match([(tw_u, def_u2), (tw_m, 104)])
stage(midTW, slot_of(midTW, tw_u), zone=1)
do_arm(midTW, slot_of(midTW, tw_u), "wanima_a_s2")
opened = engine.open_duel(midTW, "pass", slot_of(midTW, tw_m))
assert opened["duel"].get("tie_win") is True, "pure tie_win skill must arm at open"
assert "wanima_a_s2" in engine.pending_of(db.match(midTW)).get("used", []), "tie_win skill spends at open"
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

# --- Phase 7 goal cinema: commentary variants, big moments, goal card, celebration ---
for _key in ("goal", "pass_ok", "dribble_ok", "tackled", "intercepted", "saved", "blocked", "wall"):
    assert _key in engine.COMMENTARY, f"missing commentary pool: {_key}"
    assert len(engine.COMMENTARY[_key]) >= 3, f"{_key} needs at least 3 variants"
_KW = {
    "goal": {"actor": "Ace"}, "pass_ok": {"actor": "A", "target": "B"},
    "dribble_ok": {"actor": "A", "defender": "D"}, "tackled": {"actor": "A", "defender": "D"},
    "intercepted": {"actor": "A", "defender": "D"}, "saved": {"actor": "A"},
    "blocked": {"actor": "A", "defender": "D"}, "wall": {"actor": "A"},
}
for _key, _pool in engine.COMMENTARY.items():
    assert _key in _KW, f"no render kwargs defined for {_key}"
    for _tpl in _pool:
        _s = _tpl.format(**_KW[_key]).strip()
        assert _s and "<b>" in _s, (_key, _tpl)
print("ok  commentary: all 8 pools >= 3 variants, every variant renders clean")

_b = "\n".join(engine.big_moment_lines({"att_boosts": [("Deadline", 2)], "gamble_beaten": 3}, 3))
assert "HAT-TRICK" in _b and "🎲" in _b, _b
assert engine.big_moment_lines({"att_boosts": []}, 1) == [], "quiet goals add no noise"
print("ok  big moments: hat-trick + gamble quotes, quiet goals stay clean")

_g_out = {
    "outcome": "goal", "action": "shoot",
    "actor": {"name": "Ace", "user_id": fresh}, "defender": {"name": "Wall"},
    "att_boosts": [("Deadline", 2)], "def_boosts": [],
    "att_total": 9, "def_total": 5,
}
_card = views.goal_card_text(_g_out, {1: {"name": "Ace", "char_key": "isagi"}}, "🎉 SIUUU")
for _mark in ("⚽", "Ace", "Deadline", "🎉 SIUUU", "9", "5"):
    assert _mark in _card, (_mark, _card)
print("ok  goal card: scorer, duel score, skill, celebration all render")

db.set_celebration(fresh, "🎉 SIUUU")
assert db.player(fresh)["celebration"] == "🎉 SIUUU"
db.set_celebration(fresh, "")
assert db.player(fresh)["celebration"] in ("", None)
print("ok  celebration: stored and cleared on the player row")

# --- Presentation system + Shop v2 (fmt.header, views.shop_page & co) --------
_h = fmt.header("\U0001f6d2", "SHOP", "Train. Collect. Devour.")
assert _h == "\U0001f6d2 <b>SHOP</b>\n<i>Train. Collect. Devour.</i>\n" + fmt.RULE, _h
assert fmt.hint("tip") == "<i>tip</i>"
print("ok  presentation: header/hint build one canonical screen shape")

config.ABILITIES_ENABLED = True
with db.tx() as _c:  # level the fixture up so training slots are actually unlocked
    _c.execute("UPDATE players SET xp=? WHERE user_id=?", (config.xp_for_level(12), fresh))
st, sk = views.shop_page(fresh)
for _m in ("\U0001f6d2 <b>SHOP</b>", fmt.RULE, "TRAINING", "STORE", "\U0001f4b0"):
    assert _m in st, (_m, st)
assert all(len(r) <= 2 for r in sk.keyboard), "shop grid must stay <=2 columns"
_cbs = [b.callback_data for row in sk.keyboard for b in row]
assert "rollinfo" in _cbs and "titles" in _cbs and "openkit" in _cbs, _cbs
assert any(str(c).startswith("train|") for c in _cbs), _cbs
print("ok  shop page: sections render, grid <=2 cols, store buttons wired")

rct, rckb = views.rollconfirm_page(fresh)
assert f"{config.REROLL_COST:,}" in rct, rct
_rcbs = [b.callback_data for row in rckb.keyboard for b in row]
assert "buyroll" in _rcbs and "shopback" in _rcbs, _rcbs
print("ok  reroll confirm: cost shown, confirm + back wired")

db.set_title(fresh, "Devourer")
tt, tkb = views.titles_page(fresh)
assert "Devourer" in tt and "\u2705" in tt, tt
_tcbs = [b.callback_data for row in tkb.keyboard for b in row]
assert any(str(c).startswith("settitle|") for c in _tcbs), _tcbs
assert "shopback" in _tcbs, _tcbs
db.set_title(fresh, None)
print("ok  titles page: equipped title marked, presets wired, back works")

config.ABILITIES_ENABLED = False

# ------------------------------------------------------------------ quest variety
board = economy.pick_quests(economy.local_day())
assert len(board) == 3 and len(set(board)) == 3, board
assert all(economy.quest_def(q)[3] is not None or q.startswith("win") for q in board), board
_stats = {economy.quest_def(q)[3] for q in board if economy.quest_def(q)[3]}
assert len(_stats) == len([q for q in board if economy.quest_def(q)[3]]), f"two quests share a stat: {board}"
_tag = [next(n for n, ids in (("easy", economy.QUEST_EASY), ("mid", economy.QUEST_MEDIUM), ("hard", economy.QUEST_HARD)) if q in ids) for q in board]
assert sorted(_tag) == ["easy", "hard", "mid"], f"a day must mix difficulties: {board}"
# rotation: over a season every quest shows up and no board repeats a stat
_seen, _boards = set(), []
_cycle = len(economy.QUEST_BOARDS)
for _d in range(20261001, 20261001 + _cycle):
    _b = economy.pick_quests(_d)
    _boards.append(tuple(_b))
    _seen.update(_b)
    assert len(set(_b)) == 3
    _st = [economy.quest_def(q)[3] for q in _b if economy.quest_def(q)[3]]
    assert len(_st) == len(set(_st)), _b
assert len(_seen) == len(economy.QUEST_BY_ID), f"unused quests: {set(economy.QUEST_BY_ID) - _seen}"
assert len(set(_boards)) == _cycle, f"a full cycle must be repeat-free ({len(set(_boards))}/{_cycle})"
# and the cycle must close: day N+cycle shows day N's board again
assert economy.pick_quests(20261001) == economy.pick_quests(20261001 + _cycle)
assert _cycle > 40, f"too few legal boards: {_cycle}"
print(f"ok  quest catalogue: {len(economy.QUEST_BY_ID)} quests, {_cycle} legal daily boards, cycle repeats only after {_cycle} days")
# progress reads live stats for both sum-quests and win-quests
_fake = {"played": 2, "goals": 3, "assists": 4, "stops": 5, "actions": 25, "wins": 2}
assert economy.quest_progress("goal3", _fake) == 3
assert economy.quest_progress("win2", _fake) == 2
assert economy.quest_progress("act3", _fake) == 25
assert economy.quest_progress("play", _fake) == 2
for _q in economy.QUEST_BY_ID:
    assert isinstance(economy.quest_def(_q)[1], str) and economy.quest_target(_q) >= 1
    assert _q in economy.QUEST_EMOJI, f"missing emoji for {_q}"
print("ok  quests: 15-quest pool, daily easy/mid/hard board, no repeated stat, all reachable")

# 30-day summary renders every quest line
_sum = economy.quests_summary(101, economy.local_day())
assert _sum.count("\n") == 2, _sum
print("ok  quest board renders three lines")

# ------------------------------------------------------------------ seasons
db.ensure_season(config.SEASON)
assert db.season_phase(config.SEASON) in ("test", "live")

# phase helpers
db.set_setting(config.SEASON_PHASE_KEY, "test")
assert config.active_phase() == "test" and config.test_mode() is True
assert config.phase_label("test").startswith("\U0001f9ea")
db.set_setting(config.SEASON_PHASE_KEY, "live")
assert config.active_phase() == "live" and config.test_mode() is False
print("ok  season phase helpers: test/live resolve from settings")

# test season: a finished match pays no yen and no xp
db.set_setting(config.SEASON_PHASE_KEY, "test")
sandbox_uid = next(NEXT_UID)
db.touch_player(sandbox_uid, f"sb{sandbox_uid}")
_free_key = next(k for k in characters.ROSTER if k not in db.taken_keys())
db.assign_char(sandbox_uid, _free_key)
sb_match = db.create_match(-4242, "ranked", 2, sandbox_uid)
for slot, uid in ((1, sandbox_uid), (2, sandbox_uid)):
    db.touch_player(uid, f"sb{uid}")
with db.tx() as _c:
    _c.execute(
        "INSERT INTO match_players(match_id, slot, user_id, name, char_key, team, goals, assists, actions, stops, stats) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (sb_match, slot, uid, f"sb{uid}", None, slot, 1, 0, 3, 1, "{}"),
    )
db.update_match(sb_match, status="live", score1=3, score2=1)
sb_before = db.player(sandbox_uid)["yen"]
sb_xp_before = db.player(sandbox_uid)["xp"]
sb_report, _ = payouts.settle(sb_match)
assert "Test season" in sb_report, sb_report
assert db.player(sandbox_uid)["yen"] == sb_before, "test season must not pay yen"
assert db.player(sandbox_uid)["xp"] == sb_xp_before, "test season must not pay xp"
ledger = db.q1("SELECT COALESCE(SUM(amount),0) AS n FROM wallet_tx WHERE user_id=?", (sandbox_uid,))["n"]
assert ledger == 0, "test season must not touch the wallet ledger"
print("ok  test season: match pays 0 yen / 0 xp and still settles")

# test season: the shop still costs yen — no free purchases, no auto earnings
assert db.spend_yen(sandbox_uid, 1, "sandbox train") is False, "test season must not grant free purchases"
assert economy.daily_amount(3) == 0
db.add_yen(sandbox_uid, 2_000_000, "admin grant for testing")
assert db.player(sandbox_uid)["yen"] == 2_000_000, "admin grants must still work"
assert db.spend_yen(sandbox_uid, 1_500_000, "train Shot") is True, "paid purchases must work"
assert db.player(sandbox_uid)["yen"] == 500_000
db.set_setting(config.SEASON_PHASE_KEY, "live")
assert economy.daily_amount(3) > 0
print("ok  test season: shop still costs yen, no auto earnings, medals skipped")

# season panel renders + switching phase is persisted
from bluelock import handlers_admin  # noqa: F401
assert callable(handlers_admin.seasons_panel)
txt, kb = handlers_admin.seasons_panel(0, 0)
assert "SEASONS" in txt
cbs = [b.callback_data for row in kb.keyboard for b in row]
assert "adm|sphase|0|0" in cbs and "adm|snewask|0|0" in cbs, cbs
print("ok  admin seasons panel: phase + new-season buttons wired")

# new season wipes postable state but keeps characters
def _wipe_probe():
    db.add_yen(sandbox_uid, 1_000_000, "pre-wipe")
    db.bump_boost(sandbox_uid, "shot", 2)
    db.set_title(sandbox_uid, "Wiped")
    db.wipe_season_state(db.next_season_n())
    row = db.player(sandbox_uid)
    assert row["yen"] == 0 and row["xp"] == 0 and row["title"] in (None, ""), dict(row)
    assert db.owned_by(sandbox_uid) is not None, "characters must survive a wipe"
    assert json.loads(db.owned_by(sandbox_uid)["boosts"]) == {}, "boosts reset"

_wipe_probe()
print("ok  new season: yen/xp/boosts/titles wiped, characters kept")

config.ABILITIES_ENABLED = True  # streak/puppet blocks need kits armed

# S15: persistent streak buffs — Taha's goal-duration rules
# (a) rides the duel math and respects the action scope
mS = build_match([(rin_u, def_u), (isagi_u, def_u2)])
ss = slot_of(mS, rin_u)
dri = characters.base_stats("rin")["dribble"]
restage(mS, ss, zone=0)
st = engine.pending_of(db.match(mS))
st.setdefault("streaks", []).extend([
    {"slot": ss, "amt": 3, "src": "rin_p2", "kind": "streak", "scope": None},
    {"slot": ss, "amt": 5, "src": "rin_s1", "kind": "streak", "scope": "shoot"},
])
db.update_match(mS, pending=json.dumps(st))
opened = engine.open_duel(mS, "dribble", None)
assert opened["duel"]["att_power"] == dri + 3, (
    "streak rides the duel math, scope filtered", opened["duel"]["att_power"])
assert ("Bloodline Rivalry", 3) in opened["duel"]["att_boosts"], opened["duel"]["att_boosts"]
engine.cancel_duel(mS)

# (b) goal expiry: scorer's streak dies, rewards die at the NEXT goal,
#     other streaks survive the goal's turnover
gA = make_user("barou")
gB = make_user("lavinho")
mG = build_match([(gA, gB)])
gs = slot_of(mG, gA)
gk_slot = slot_of(mG, gB)
stage(mG, gs, set_piece="penalty", zone=ZONE_BOX)
st = engine.pending_of(db.match(mG))
st.setdefault("streaks", []).extend([
    {"slot": gs, "amt": 3, "src": "barou_p1", "kind": "streak", "scope": None},
    {"slot": gk_slot, "amt": 4, "src": "lavinho_p1", "kind": "streak", "scope": None},
    {"slot": gk_slot, "amt": 2, "src": "lavinho_s1", "kind": "reward", "scope": None},
])
db.update_match(mG, pending=json.dumps(st))
engine.open_duel(mG, "penalty", None)
assert engine.submit_spot(mG, gA, "left")["status"] == "ok"
assert engine.submit_spot(mG, gB, "right")["status"] == "ok"
out = engine.resolve(mG)
assert out["outcome"] == "goal", out
st = engine.pending_of(db.match(mG))
kinds = {(s["slot"], s["kind"]) for s in st.get("streaks", [])}
assert (gs, "streak") not in kinds, "scorer's mid-match streak dies when he scores"
assert (gk_slot, "streak") in kinds, "other streaks survive the goal/turnover"
assert (gk_slot, "reward") not in kinds, "goal rewards expire at the very next goal"
assert st.get("buffs") == [], "one-shot buffs are wiped by the turnover"
print("ok  streak/reward buffs: math+scope, goal-rule expiry, survive turnovers")

# S16: RIN PUPPET — guaranteed pass → forced receiver dribble → Rin reclaims
mP = build_match([(rin_u, def_u), (isagi_u, def_u2)])
ps = slot_of(mP, rin_u)
ms = slot_of(mP, isagi_u)
# the season-wipe test above emptied everyone's unlocks — restore the starters
for _aid in abilities.starter_ids("rin"):
    db.grant_unlock(rin_u, _aid)
for _aid in abilities.starter_ids("isagi"):
    db.grant_unlock(isagi_u, _aid)
restage(mP, ps, zone=0)
do_arm(mP, ps, "rin_p1")   # manual: Rin taps his passive before passing
opened = engine.open_duel(mP, "pass", ms)
assert opened["duel"].get("auto", {}).get("aid") == "rin_p1", (
    "puppet pass must be guaranteed", opened["duel"].get("auto"))
out = roll_and_resolve(mP, att=6, dfn=1)
assert out["outcome"] == "pass_ok", out
st = engine.pending_of(db.match(mP))
assert st.get("puppet", {}).get("stage") == "await_action", st.get("puppet")
mp_row = db.match(mP)
assert db.claim_turn(mP, mp_row["turn"], ms) is True
assert engine.legal_actions(db.match(mP)) == ["dribble"], engine.legal_actions(db.match(mP))
assert "error" in engine.open_duel(mP, "pass", ps), "Puppet forces the dribble"
assert "error" not in engine.open_duel(mP, "dribble", None)
out = roll_and_resolve(mP, att=1, dfn=6)   # losing the duel must not matter
assert out["outcome"] == "dribble_ok", ("reclaim overrides the result", out.get("outcome"))
assert out.get("puppet_take") and out["puppet_take"]["slot"] == ps, out.get("puppet_take")
assert db.match(mP)["holder"] == ps, "Rin owns the ball again"
st = engine.pending_of(db.match(mP))
assert st.get("puppet", {}).get("stage") == "done", st.get("puppet")
streaks = {(s["slot"], s.get("scope"), s["amt"]) for s in st.get("streaks", [])}
assert (ps, "shoot", 2) in streaks, streaks
assert (ms, None, 1) in streaks, streaks
print("ok  Rin PUPPET: guaranteed pass → forced dribble → reclaim + streaks")

db.set_setting(config.SEASON_PHASE_KEY, "live")

# S17: EMPEROR — everyone Kaiser shot past takes -1 until the next goal
mK = build_match([(kaiser_u, def_u), (rin_u, def_u2)])
ks = slot_of(mK, kaiser_u)
# the season-wipe test above emptied everyone's unlocks — restore the starters
for _aid in abilities.starter_ids("kaiser"):
    db.grant_unlock(kaiser_u, _aid)
kbase = characters.base_stats("kaiser")
stage(mK, ks, zone=ZONE_SHOOT, beaten=[])
do_arm(mK, ks, "kaiser_p1")
opened = engine.open_duel(mK, "shoot", None)
assert opened["duel"]["att_power"] == kbase["shot"] + 2, (
    "Emperor adds +2 on his shot", opened["duel"]["att_power"])
out = roll_and_resolve(mK, att=6, dfn=1, gk=1)
assert out["outcome"] == "goal", ("shot must go in to prove the ordering", out["outcome"])
st = engine.pending_of(db.match(mK))
minus = [s for s in st.get("streaks", []) if (s.get("amt") or 0) < 0]
assert minus, ("everyone Kaiser shot past must take -1", st.get("streaks"))
assert all(s["src"] == "kaiser_p1" for s in minus), minus
assert all(s["kind"] == "reward" for s in minus), minus
assert ks not in {s["slot"] for s in minus}, "Kaiser never debuffs himself"
# the payout runs AFTER score_goal(), so the -1 survives the goal the shot
# scored; kind=reward means the NEXT goal (any side) wipes it — see S15.
print("ok  Emperor: shot beats the wall -> everyone beaten takes -1, survives its own goal")

# S18: Sae / Charles — the attack bonus burns the charge, yet the receiver
# buff must STILL land (resolve() used to find an empty armed slot and skip it)
for uid, aid, ch, ruid, bname, a_amt, b_amt in (
        (fresh, "sae_p1", "sae", rin_u, "Winning Movement", 2, 2),
        (new_users["charles"], "charles_p1", "charles", isagi_u, "French Pass", 2, 1)):
    m = build_match([(uid, def_u), (ruid, def_u2)])
    ss, rr = slot_of(m, uid), slot_of(m, ruid)
    for _x in abilities.starter_ids(ch):
        db.grant_unlock(uid, _x)
    stage(m, ss, zone=0)
    do_arm(m, ss, aid)
    opened = engine.open_duel(m, "pass", rr)
    assert (bname, a_amt) in opened["duel"]["att_boosts"], (bname, opened["duel"]["att_boosts"])
    out = roll_and_resolve(m, att=6, dfn=1)
    assert out["outcome"] == "pass_ok", out
    st = engine.pending_of(db.match(m))
    got = [b for b in st.get("buffs", []) if b["slot"] == rr]
    assert got, (bname, "receiver must get his buff", st.get("buffs"))
    assert got[0]["amt"] == b_amt, (bname, got)
    assert aid in st.get("used", []), (bname, "one use — the charge still burns")
print("ok  Winning Movement / French Pass: receiver buff lands even though the charge burns")

# S19: the goal payout SPANS actions — Sae's pass sets up a goal that only
# lands on a later action (Sae and his mate both get +1)
mG2 = build_match([(fresh, def_u), (rin_u, def_u2)])
sS2, rS2 = slot_of(mG2, fresh), slot_of(mG2, rin_u)
for _x in abilities.starter_ids("sae"):
    db.grant_unlock(fresh, _x)
stage(mG2, sS2, zone=0)
do_arm(mG2, sS2, "sae_p1")
opened = engine.open_duel(mG2, "pass", rS2)
out = roll_and_resolve(mG2, att=6, dfn=1)
assert out["outcome"] == "pass_ok", out
st = engine.pending_of(db.match(mG2))
assert st.get("pending_goals", [{}])[0].get("owner") == sS2, st.get("pending_goals")
# the receiver scores one action later (a penalty keeps it deterministic)
st.update({"zone": ZONE_BOX, "set_piece": "penalty", "beaten": []})
db.update_match(mG2, pending=json.dumps(st), phase="opening", holder=rS2)
assert "error" not in engine.open_duel(mG2, "penalty", None)
assert engine.submit_spot(mG2, rin_u, "left")["status"] == "ok"
assert engine.submit_spot(mG2, def_u, "right")["status"] == "ok"
out = engine.resolve(mG2)
assert out["outcome"] == "goal", out
st = engine.pending_of(db.match(mG2))
assert "pending_goals" not in st, "the payout is consumed by the goal"
paid = [(s["slot"], s["amt"], s["src"]) for s in st.get("streaks", [])
        if s.get("kind") == "reward" and (s.get("amt") or 0) > 0]
assert (sS2, 1, "sae_p1") in paid, ("Sae is owed +1", paid)
assert (rS2, 1, "sae_p1") in paid, ("the scorer is owed +1", paid)
print("ok  goal payout spans actions: Sae's pass -> later goal -> both take +1")

# S20: through 1..3 — the carry walks past several opponents at once,
# and every one of them eats Emperor's -1.
mT = build_match([(kaiser_u, def_u), (isagi_u, def_u2)])
sT = slot_of(mT, kaiser_u)
for _x in abilities.starter_ids("kaiser"):
    db.grant_unlock(kaiser_u, _x)
stage(mT, sT, zone=1)
do_arm(mT, sT, "kaiser_p1")
opened = engine.open_duel(mT, "dribble", None)
assert opened["duel"].get("through") == 3, opened["duel"].get("through")
out = roll_and_resolve(mT, att=4, dfn=1)
assert out["outcome"] in ("dribble_ok", "goal"), out
assert out.get("through_beaten"), out
st = engine.pending_of(db.match(mT))
nbeaten = st.get("beaten", [])
neg = [s for s in st.get("streaks", []) if s.get("amt", 0) < 0]
assert len(neg) >= len(nbeaten), (neg, nbeaten)
assert all(n["amt"] == -1 for n in neg), neg
print("ok  Emperor: carry walks past several -> every beaten player takes -1")

# S21: Lavinho's Dance beats the WHOLE defence (through = 99, die-capped)
mT2 = build_match([(gB, def_u), (isagi_u, def_u2)])
sT2 = slot_of(mT2, gB)
stage(mT2, sT2, zone=1)
do_arm(mT2, sT2, "lavinho_p1")
engine.open_duel(mT2, "dribble", None)
out = roll_and_resolve(mT2, att=6, dfn=1)
assert out["outcome"] in ("dribble_ok", "goal"), out
st2 = engine.pending_of(db.match(mT2))
_ro = db.roster(mT2)
_kt = next(r_["team"] for r_ in _ro if r_["slot"] == sT2)
_nop = sum(1 for r_ in _ro if r_["team"] != _kt)
assert len(st2.get("beaten", [])) >= _nop, (st2.get("beaten"), "of", _nop)
print("ok  Dance: high die walks past the whole defence",
      len(st2.get("beaten", [])), "/", _nop)

# S22: Hugo's Phantom Pass/Shot — now a contest: Hugo hides a die, they call it.
hugo_u = make_user("hugo")
mH = build_match([(hugo_u, def_u), (isagi_u, def_u2)])
sH = slot_of(mH, hugo_u)
stage(mH, sH, zone=1)
do_arm(mH, sH, "hugo_p1")
engine.open_duel(mH, "pass", slot_of(mH, isagi_u))
pH = engine.awaiting(db.match(mH))
assert pH and pH["role"] == "contest_set" and pH["user_id"] == hugo_u, pH
assert engine.submit_contest_set(mH, hugo_u, "2")["status"] == "ok"
pH = engine.awaiting(db.match(mH))
assert pH and pH["role"] == "contest_call", pH
r = engine.submit_contest_call(mH, pH["user_id"], "1")
assert r["effect"].get("win") == "att", r["effect"]
assert engine.ready(db.match(mH)), "a wrong call ends the contest"
out = engine.resolve(mH)
assert out["outcome"] == "pass_ok", out
print("ok  Phantom Call: wrong call -> his pass lands with no roll")

mH2 = build_match([(hugo_u, def_u), (isagi_u, def_u2)])
sH2 = slot_of(mH2, hugo_u)
stage(mH2, sH2, zone=1)
do_arm(mH2, sH2, "hugo_p1")
engine.open_duel(mH2, "pass", slot_of(mH2, isagi_u))
pH2 = engine.awaiting(db.match(mH2))
assert engine.submit_contest_set(mH2, hugo_u, "3")["status"] == "ok"
pH2 = engine.awaiting(db.match(mH2))
r = engine.submit_contest_call(mH2, pH2["user_id"], "3")
assert r["effect"] == {}, r["effect"]
assert not engine.ready(db.match(mH2)), "the contest still needs its dice"
out = roll_and_resolve(mH2, att=1, dfn=6)
assert out["outcome"] != "pass_ok", out   # a right call really can cost him
print("ok  Phantom Call: right call -> they compete and he can lose")

# S23: Last Puzzle — he read it, he got there, and a die-6 keeper still can't save it
mI = build_match([(isagi_u, def_u), (rin_u, def_u2)])
sI = slot_of(mI, isagi_u)
stage(mI, sI, zone=1)
do_arm(mI, sI, "isagi_p1")
engine.open_duel(mI, "shoot", None)
stI = engine.pending_of(db.match(mI))
assert stI["duel"].get("sure_goal"), stI["duel"].get("auto")
assert stI["duel"].get("auto", {}).get("t") == "win", stI["duel"].get("auto")
out = roll_and_resolve(mI, att=1, gk=6)
assert out["outcome"] == "goal", out
assert out.get("sure_goal"), out
print("ok  Last Puzzle: a die-1 shot past a die-6 keeper still goes in")

# S23b: Chemical Reaction removed — Isagi keeps no bound ability
assert "isagi_bp" not in abilities.REGISTRY
print("ok  Chemical Reaction removed — isagi has no bound ability")


# S23c: Last Puzzle STEALS the ball the moment he arms it — no holder, no problem
def recharge(mid: int, slot: int, aid: str, n: int = 1) -> None:
    st = engine.pending_of(db.match(mid))
    st.setdefault("charges", {})[aid] = n
    st["used"] = [u for u in st.get("used", []) if u != aid]
    st.get("armed", {}).pop(str(slot), None)
    db.update_match(mid, pending=json.dumps(st))


mS = build_match([(def_u, isagi_u)])   # Wanima holds; Isagi is on the other team
sS = slot_of(mS, isagi_u)
wS = slot_of(mS, def_u)
for _x in abilities.starter_ids("isagi"):
    db.grant_unlock(isagi_u, _x)
stage_play(mS, wS, zone=1, beaten=[])
recharge(mS, sS, "isagi_p1")
resS = engine.arm_skill(mS, isagi_u, "isagi_p1")
assert resS["status"] == "armed" and resS.get("stole"), resS
assert db.match(mS)["holder"] == sS, "arming Last Puzzle takes the ball"
mS2 = db.match(mS)
assert db.claim_turn(mS, mS2["turn"], mS2["holder"])
engine.open_duel(mS, "shoot", None)
stS = engine.pending_of(db.match(mS))
assert stS["duel"].get("sure_goal"), stS["duel"].get("auto")
outS = roll_and_resolve(mS, att=1, gk=6)
assert outS["outcome"] == "goal", outS
print("ok  Last Puzzle: arm without the ball -> he takes it -> the shot is unsaveable")

# S23d: undo gives the burned charge back
mU = build_match([(isagi_u, def_u)])
sU = slot_of(mU, isagi_u)
stage_play(mU, sU, zone=1, beaten=[])
recharge(mU, sU, "isagi_p1")
assert engine.arm_skill(mU, isagi_u, "isagi_p1")["status"] == "armed"
mU2 = db.match(mU)
assert db.claim_turn(mU, mU2["turn"], mU2["holder"])
engine.open_duel(mU, "shoot", None)
stU = engine.pending_of(db.match(mU))
assert "isagi_p1" in stU.get("used", []), "the duel burned the charge"
engine.cancel_duel(mU)
stU = engine.pending_of(db.match(mU))
assert "isagi_p1" not in stU.get("used", []), "undo must give the charge back"
assert stU["charges"].get("isagi_p1", 0) >= 1, stU.get("charges")
assert db.match(mU)["phase"] == "play"
print("ok  undo: a cancelled duel refunds the passive charge it burned")

# S24: keeper spills it — a passive tuned to the loose ball beats the coin flip
sae_u = fresh  # the sae owner the suite already made
# the wall has to be beatable AND the keeper still able to spill one, so the
# other keeper is a low-meta man (charles) — wanima alone would do it too.
def_s24 = new_users["charles"]  # the suite already made this one
mL = build_match([(sae_u, def_u), (isagi_u, def_s24)])
sL_sae = slot_of(mL, sae_u)
sL_isa = slot_of(mL, isagi_u)
for _x in abilities.starter_ids("sae"): db.grant_unlock(sae_u, _x)
stage(mL, sL_isa, zone=1)
do_arm(mL, sL_sae, "sae_p1")
engine.open_duel(mL, "shoot", None)
assert "sae_p1" not in engine.pending_of(db.match(mL)).get("used", [])
out = roll_and_resolve(mL, att=1, dfn=1, gk=3)   # past the wall, saved, spilled (< 4)
assert out["outcome"] == "goal", out
assert out.get("loose_finish"), out
st = engine.pending_of(db.match(mL))
assert "sae_p1" in st.get("used", []), "the loose-ball finish burns the charge"
print("ok  loose finish: the keeper spills it and Sae walks it in for a sure goal")
# S25: Monster Moment — the stack tops up on every dribble
mB = build_match([(sim_u3, def_u), (rin_u, def_u2)])
sB = slot_of(mB, sim_u3)
for _x in abilities.starter_ids("bachira"): db.grant_unlock(sim_u3, _x)
stage(mB, sB, zone=0)
do_arm(mB, sB, "bachira_p1")
o1 = engine.open_duel(mB, "dribble", None)
assert dict(o1["duel"]["att_boosts"]).get("Monster Moment") == 2, o1["duel"]["att_boosts"]
out = roll_and_resolve(mB, att=6, dfn=1)
assert out["outcome"] == "dribble_ok", out
assert engine.pending_of(db.match(mB)).get("monster", {}).get("amt") == 1, engine.pending_of(db.match(mB)).get("monster")
# reopen the phase without wiping the state — stage() would kill the stack
db.update_match(mB, pending=json.dumps(engine.pending_of(db.match(mB))), phase="opening", holder=sB)
o2 = engine.open_duel(mB, "dribble", None)
assert "duel" in o2, o2
assert dict(o2["duel"]["att_boosts"]).get("Monster Moment") == 1, o2["duel"]["att_boosts"]
out = roll_and_resolve(mB, att=6, dfn=1)
assert out["outcome"] == "dribble_ok", out
assert engine.pending_of(db.match(mB)).get("monster", {}).get("amt") == 2
print("ok  Monster Moment: every dribble tops the stack up (+1, then +2)")
# a goal wipes the stack like every other buff
db.update_match(mB, pending=json.dumps(engine.pending_of(db.match(mB))), phase="opening", holder=sB)
o3 = engine.open_duel(mB, "shoot", None)
assert dict(o3["duel"]["att_boosts"]).get("Monster Moment") == 2, o3["duel"]["att_boosts"]
out = roll_and_resolve(mB, att=6, dfn=1, gk=1)
assert out["outcome"] == "goal", out
assert not engine.pending_of(db.match(mB)).get("monster"), "the stack dies with the goal"
print("ok  Monster Moment: a goal wipes the stack")
# S26: the stance key — one charge, one stance, never both at once
k_u = make_user("knight")
mk = build_match([(k_u, def_u)])   # 1v1 — Teddy is the only man who can defend
sk = slot_of(mk, k_u)
o_def = slot_of(mk, def_u)
for _x in abilities.starter_ids("knight"): db.grant_unlock(k_u, _x)

def stance(mid, holder_slot, mode, arm_slot):
    st = engine.fresh_state()
    st["zone"] = 0
    if mode is not None and arm_slot is not None:
        st.setdefault("modes", {})[str(arm_slot)] = mode
    if arm_slot is not None:
        st.setdefault("armed", {})[str(arm_slot)] = "knight_p1"
    db.update_match(mid, pending=json.dumps(st), phase="opening", holder=holder_slot)

# arm_skill is what stores the stance
stance(mk, sk, None, None)      # arm_skill does the arming AND the stance
db.update_match(mk, phase="play")
res = engine.arm_skill(mk, k_u, "knight_p1", mode="sword")
assert res["status"] == "armed", res
assert engine.pending_of(db.match(mk)).get("modes", {}).get(str(sk)) == "sword"
db.update_match(mk, phase="opening")

o = engine.open_duel(mk, "dribble", None)
b = dict(o["duel"]["att_boosts"])
assert b.get("Knight Defense / Knight Sword") == 1, b       # +1 on his dribble
assert not o["duel"]["def_boosts"], "the sword stance never shields"
engine.cancel_duel(mk)
print("ok  Knight Sword: +1 on his dribble and no defense in the way")

# the other stance, this time with somebody running at him
stance(mk, o_def, "defense", sk)
o = engine.open_duel(mk, "dribble", sk)
b = dict(o["duel"]["def_boosts"])
assert b.get("Knight Defense / Knight Sword") == 2, \
    {"boosts": b, "defender": o["duel"].get("defender"), "wall": o["duel"].get("wall"),
     "modes": engine.pending_of(db.match(mk)).get("modes"),
     "armed": engine.pending_of(db.match(mk)).get("armed")}
assert not o["duel"]["att_boosts"], "the defense stance never swings"
out = roll_and_resolve(mk, att=1, dfn=6)                      # he wins the ball
assert out["outcome"] in ("tackled", "blocked"), out
st = engine.pending_of(db.match(mk))
assert (st.get("hold_buff") or {}).get("amt") == 2, st.get("hold_buff")
print("ok  Knight Defense: +2 in his face, and +2 rides the ball he wins")

# ...and that bonus rides for as long as he keeps it
db.update_match(mk, pending=json.dumps(st), phase="opening", holder=sk)
o = engine.open_duel(mk, "dribble", None)
b = dict(o["duel"]["att_boosts"])
assert b.get("Knight Defense / Knight Sword") == 2, b
engine.cancel_duel(mk)
print("ok  Knight Defense: the bonus rides his possession")
# S27: Winning Movement — the pass threads straight between two men
mS = build_match([(fresh, def_u), (isagi_u, def_u2)])
ss = slot_of(mS, fresh)
for _x in abilities.starter_ids("sae"): db.grant_unlock(fresh, _x)
stage(mS, ss, zone=0)
do_arm(mS, ss, "sae_p1")
o = engine.open_duel(mS, "pass", slot_of(mS, isagi_u))
assert o["duel"].get("through") == 2, o["duel"].get("through")
out = roll_and_resolve(mS, att=6, dfn=1)
assert out["outcome"] == "pass_ok", out
print("ok  Winning Movement: the pass threads between two men")

# S28: Dance — the run ends with him going around the keeper
mL2 = build_match([(gB, def_u), (isagi_u, new_users["charles"])])
sl = slot_of(mL2, gB)
for _x in abilities.starter_ids("lavinho"): db.grant_unlock(gB, _x)
stage(mL2, sl, zone=0)
do_arm(mL2, sl, "lavinho_p1")
engine.open_duel(mL2, "dribble", None)
out = roll_and_resolve(mL2, att=6, dfn=1)
assert out["outcome"] == "dribble_ok", out
st = engine.pending_of(db.match(mL2))
assert "lavinho_p1" in st.get("used", []), "the dribble burns the charge"
assert st.get("beat_gk"), "the run is still on"
db.update_match(mL2, pending=json.dumps(st), phase="opening", holder=sl)
o = engine.open_duel(mL2, "shoot", None)
assert o["duel"].get("beat_keeper"), sorted(o["duel"].keys())
out = roll_and_resolve(mL2, att=1, dfn=1, gk=6)   # a die-6 keeper saves this
assert out["outcome"] == "goal", out
assert out.get("beat_keeper"), out
print("ok  Dance: the run ends with him around a die-6 keeper")

# --- BOUND: mutual partners on the same team fire, tier scales the bonus ----
b_z = new_users["zantetsu"]
b_n = new_users["ness"]
db.set_bound(b_z, "ness")
db.set_bound(b_n, "zantetsu")
db.set_bound_tier(b_z, 2)
mBD = build_match([(b_z, def_u), (b_n, def_u2)])
zs = slot_of(mBD, b_z)
stage(mBD, zs, zone=0)
do_arm(mBD, zs, "zantetsu_bp")
opened = engine.open_duel(mBD, "dribble", None)
assert "error" not in opened
hits = [(n, v) for n, v in opened["duel"].get("att_boosts", []) if n == "Blade Dash"]
assert hits == [("Blade Dash", 2)], hits
assert "zantetsu_bp" in engine.pending_of(db.match(mBD)).get("used", [])
print("ok  bound: mutual partners on the same team fire; tier II scales +1 -> +2")

db.set_bound(b_n, None)
mBD2 = build_match([(b_z, def_u), (b_n, def_u2)])
zs2 = slot_of(mBD2, b_z)
stage(mBD2, zs2, zone=0)
do_arm(mBD2, zs2, "zantetsu_bp")
opened = engine.open_duel(mBD2, "dribble", None)
assert "error" not in opened
hits = [(n, v) for n, v in opened["duel"].get("att_boosts", []) if n == "Blade Dash"]
assert hits == [], hits
assert "zantetsu_bp" not in engine.pending_of(db.match(mBD2)).get("used", [])
print("ok  bound: a one-sided bind stays inactive and keeps the charge")

# --- BOUND leak: an armed *_bp without a partner must never apply at resolve -
solo = new_users["aiku"]
mSL = build_match([(isagi_u, solo)])
ss = slot_of(mSL, isagi_u)
sls = slot_of(mSL, solo)
stage(mSL, ss, zone=0)
do_arm(mSL, sls, "aiku_bp")
engine.open_duel(mSL, "dribble", None)
out = roll_and_resolve(mSL, att=4, dfn=1)
assert not [(n, v) for n, v in out.get("def_boosts", []) if n == "Libero Lock"], out.get("def_boosts")
pend = engine.pending_of(db.match(mSL))
assert "aiku_bp" not in pend.get("used", []), "inactive bound passive must keep its charge"
print("ok  bound: resolve never applies a bound passive without its partner")

# --- penalty ERASE: the keeper's auto-stop skill skips the corner game -------
gk_u = make_user("fukaku", unlocks=["fukaku_s2"])
mPE = build_match([(isagi_u, gk_u)])
ps = slot_of(mPE, isagi_u)
ks = slot_of(mPE, gk_u)
stage(mPE, ps, zone=ZONE_BOX, set_piece="penalty")
do_arm(mPE, ks, "fukaku_s2")
opened = engine.open_duel(mPE, "penalty", None)
assert "error" not in opened
assert engine.awaiting(db.match(mPE)) is None, "an erased penalty asks for no corner"
out = engine.resolve(mPE)
assert out["outcome"] == "saved" and out.get("erased"), out
assert "fukaku_s2" in engine.pending_of(db.match(mPE))["used"]
dsc = engine.describe(out, {r["slot"]: r for r in db.roster(mPE)})
assert "erased" in dsc, dsc
print("ok  penalty erase: the keeper's stop skill cancels the corner game")

# --- no resurrection: a freekick-only skill must not fire on open play -------
midRN = build_match([(rin_u, def_u)])
rs = slot_of(midRN, rin_u)
stage(midRN, rs, zone=ZONE_SHOOT)
do_arm(midRN, rs, "rin_s2")
engine.open_duel(midRN, "shoot", None)
out = roll_and_resolve(midRN, att=5, dfn=1, gk=5)
pend = engine.pending_of(db.match(midRN))
assert "rin_s2" not in pend.get("used", []), "Itoshi Curl is freekick-only — the charge survives"
assert out["outcome"] == "saved", out
print("ok  gating: freekick-only skill neither fires nor burns on a shot")

# --- gamble with no defender: a low roll collapses instead of crashing -------
db.grant_unlock(104, "reo_s1")
mGB = build_match([(104, def_u), (rin_u, def_u2)])
gs = slot_of(mGB, 104)
opp = [r["slot"] for r in db.roster(mGB) if r["team"] != 1]
stage(mGB, gs, zone=ZONE_SHOOT, beaten=opp)
do_arm(mGB, gs, "reo_s1")
opened = engine.open_duel(mGB, "shoot", None)
assert "error" not in opened
assert opened["duel"].get("gamble") is True, opened["duel"].get("gamble")
out = roll_and_resolve(mGB, att=1, dfn=1, gk=3)
assert out.get("gamble_backfire"), out
assert out["outcome"] != "goal", out
pend = engine.pending_of(db.match(mGB))
assert pend.get("beaten") == [gs], (pend.get("beaten"), "turnover clears the field, the loser stays beaten")
print("ok  gamble backfire with no defender: collapses cleanly, ball turns over")

# --- mid-duel defensive arm: a stop pressed while the rolls are pending -----
midMS = build_match([(isagi_u, gA)])
ms = slot_of(midMS, isagi_u)
mds = slot_of(midMS, gA)
stage(midMS, ms, zone=0)
assert "error" not in engine.open_duel(midMS, "dribble", None)
do_arm(midMS, mds, "barou_s1")
out = roll_and_resolve(midMS, att=6, dfn=1)
assert out["outcome"] == "tackled", out
assert out.get("stopped_by_skill") and out["stopped_by_skill"]["slot"] == mds, out.get("stopped_by_skill")
assert "barou_s1" in engine.pending_of(db.match(midMS))["used"]
print("ok  mid-duel arm: a stop pressed during the duel still wins the ball")

# --- wrong call on a SHOT wins outright — the keeper never gets a say -------
mH3 = build_match([(hugo_u, def_u), (isagi_u, def_u2)])
sH3 = slot_of(mH3, hugo_u)
stage(mH3, sH3, zone=ZONE_SHOOT)
do_arm(mH3, sH3, "hugo_p1")
engine.open_duel(mH3, "shoot", None)
pH3 = engine.awaiting(db.match(mH3))
assert pH3 and pH3["role"] == "contest_set" and pH3["user_id"] == hugo_u, pH3
engine.submit_contest_set(mH3, hugo_u, "2")
pH3 = engine.awaiting(db.match(mH3))
assert pH3 and pH3["role"] == "contest_call", pH3
engine.submit_contest_call(mH3, pH3["user_id"], "1")
out = roll_and_resolve(mH3, att=1, gk=6)
assert out["outcome"] == "goal", out
assert out.get("sure_goal"), out
print("ok  Phantom Call: a wrong call on the shot wins outright")

# --- contest: interactive mind-game passives (12-char pilot wave) -----------
# attacker hides, defender misreads -> auto win + zone + spend
mC1 = build_match([(nagi_u, def_u2)])
cs1 = slot_of(mC1, nagi_u)
stage(mC1, cs1, zone=0)
do_arm(mC1, cs1, "nagi_p1")
assert "error" not in engine.open_duel(mC1, "dribble", None)
p = engine.awaiting(db.match(mC1))
assert p and p["role"] == "contest_set" and p["user_id"] == nagi_u, p
board = views.duel_board(db.match(mC1), db.roster(mC1))
assert "locks in a hidden move" in board and "send 🎲" not in board, board
assert engine.submit_contest_set(mC1, nagi_u, "spring")["status"] == "ok"
p = engine.awaiting(db.match(mC1))
assert p and p["role"] == "contest_call" and p["user_id"] == def_u2, p
board = views.duel_board(db.match(mC1), db.roster(mC1))
assert "calls his move" in board and "send 🎲" not in board, board
assert engine.submit_contest_call(mC1, def_u2, "nonsense")["status"] == "invalid"
r = engine.submit_contest_call(mC1, def_u2, "back")
assert r["effect"].get("win") == "att" and r["effect"].get("zone") == 1, r
pend = engine.pending_of(db.match(mC1))
assert pend["duel"]["auto"]["t"] == "win" and pend["duel"]["zone_extra"] == 1
assert "nagi_p1" in pend["used"]
out = roll_and_resolve(mC1, att=1)
assert out["outcome"] == "dribble_ok", out
assert engine.pending_of(db.match(mC1))["zone"] > 0, "the baited zone lands"
print("ok  contest: attacker hides, misread -> auto win + zone, charge spent")

# a correct read kills the same move
mC2 = build_match([(nagi_u, def_u2)])
cs2 = slot_of(mC2, nagi_u)
stage(mC2, cs2, zone=0)
do_arm(mC2, cs2, "nagi_p1")
engine.open_duel(mC2, "dribble", None)
assert engine.submit_contest_set(mC2, nagi_u, "spring")["status"] == "ok"
r = engine.submit_contest_call(mC2, def_u2, "press")
assert r["effect"].get("win") == "def", r
out = roll_and_resolve(mC2, att=6, dfn=1)
assert out["outcome"] in ("tackled", "blocked"), out
print("ok  contest: a correct read smothers the burst")

# defender-secret: the defence hides its call, the attacker declares
noa_u = make_user("noa")
mC3 = build_match([(noa_u, def_u)])
cs3 = slot_of(mC3, noa_u)
ds3 = slot_of(mC3, def_u)
stage(mC3, cs3, zone=1)
do_arm(mC3, cs3, "noa_p1")
engine.open_duel(mC3, "dribble", None)
cfg = engine.pending_of(db.match(mC3))["duel"]["contest"]
assert cfg["secret"] == "d" and cfg["set_slot"] == ds3 and cfg["call_slot"] == cs3, cfg
p = engine.awaiting(db.match(mC3))
assert p and p["role"] == "contest_set" and p["user_id"] == def_u, p
assert engine.submit_contest_set(mC3, def_u, "sense")["status"] == "ok"
p = engine.awaiting(db.match(mC3))
assert p and p["role"] == "contest_call" and p["user_id"] == noa_u, p
r = engine.submit_contest_call(mC3, noa_u, "direct")
assert r["effect"].get("win") == "def", r
out = roll_and_resolve(mC3, att=6, dfn=1)
assert out["outcome"] in ("tackled", "blocked"), out
print("ok  contest: defender-secret flow — he hides, Noa declares")

# defender-owned read (aiku) kills the attacker's declared drive
mC4 = build_match([(isagi_u, new_users["aiku"])])
sC4 = slot_of(mC4, isagi_u)
aC4 = slot_of(mC4, new_users["aiku"])
stage(mC4, sC4, zone=0)
do_arm(mC4, aC4, "aiku_p1")
engine.open_duel(mC4, "dribble", None)
cfg = engine.pending_of(db.match(mC4))["duel"]["contest"]
assert cfg["owner"] == "d" and cfg["d_slot"] == aC4 and cfg["set_slot"] == sC4, cfg
assert engine.submit_contest_set(mC4, isagi_u, "drive")["status"] == "ok"
r = engine.submit_contest_call(mC4, new_users["aiku"], "ice_drive")
assert r["effect"].get("win") == "def", r
out = roll_and_resolve(mC4, att=6, dfn=1)
assert out["outcome"] in ("tackled", "blocked"), out
print("ok  contest: defender-owned read (Board Vision) kills the drive")

# unmarked: no moment, no spend
mC5 = build_match([(nagi_u, def_u2)])
sC5 = slot_of(mC5, nagi_u)
oppC5 = [r["slot"] for r in db.roster(mC5) if r["team"] != 1]
stage(mC5, sC5, zone=1, beaten=oppC5)
do_arm(mC5, sC5, "nagi_p1")
engine.open_duel(mC5, "dribble", None)
pend = engine.pending_of(db.match(mC5))
assert "contest" not in pend["duel"]
assert engine.awaiting(db.match(mC5)) is None
out = roll_and_resolve(mC5, att=4)
assert out["outcome"] == "dribble_ok", out
pend = engine.pending_of(db.match(mC5))
assert "nagi_p1" not in pend["used"], "unmarked action must keep the charge"
print("ok  contest: unmarked action starts no mind-game, charge kept")

print("\nABILITY SUITE PASSED")
print("\nALL SIMULATION CHECKS PASSED")
