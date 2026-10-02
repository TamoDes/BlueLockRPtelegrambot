import json
import random

from . import abilities, db
from .abilities import kits_by_user
from .characters import effective_stats, role_of
from .config import (
    BOUND_ENABLED,
    PASSIVES_MANUAL,
    DICE_FACES,
    GOAL_TARGET,
    KEEPER_CATCH_ROLL,
    KEEPER_NAME,
    KEEPER_POWER,
    PENALTY_NERVE_SPAN,
    PENALTY_TARGETS,
    STAT_NAME,
    ZONE_BOX,
    ZONE_SHOOT,
    max_turns,
)

ACTION_STAT = {
    "pass": "passing",
    "dribble": "dribble",
    "shoot": "shot",
    "freekick": "freekick",
    "penalty": "shot",
    "cross": "freekick",
}
ACTION_NAME = {
    "pass": "Pass",
    "dribble": "Dribble",
    "shoot": "Shoot",
    "freekick": "Free Kick",
    "penalty": "Penalty",
    "cross": "Cross",
    "advance": "Advance",
}
SET_PIECES = ("freekick", "penalty")
KEEPER_ACTIONS = ("shoot", "freekick")


def slot_stats(row) -> dict[str, int]:
    stored = json.loads(row["stats"] or "{}")
    if stored:
        return stored
    return effective_stats(row["char_key"], {}) if row["char_key"] else {s: 3 for s in STAT_NAME}


def marker(roster: list, team: int, beaten: list | None = None):
    out = set(beaten or ())
    opponents = [r for r in roster if r["team"] != team and r["slot"] not in out]
    if not opponents:
        return None
    return max(opponents, key=lambda r: slot_stats(r)["meta"])


def defender_team(actor) -> int:
    return 2 if actor["team"] == 1 else 1


def loose_ball_to(roster: list, actor, beaten: list | None = None):
    opponents = [r for r in roster if r["team"] != actor["team"]]
    return random.choice(opponents) if opponents else actor


def team_captain(roster: list, team: int):
    mates = [r for r in roster if r["team"] == team]
    return min(mates, key=lambda r: r["slot"]) if mates else None


def pending_of(match) -> dict:
    return json.loads(match["pending"] or "{}")


def race_to_goals(match) -> bool:
    return match["mode"] == "ranked"


def turn_limit(match) -> int:
    return max_turns(match["size"], match["mode"])


def over(match) -> bool:
    if match["turn"] > turn_limit(match):
        return True
    if not race_to_goals(match):
        return False
    return max(match["score1"], match["score2"]) >= GOAL_TARGET


def zone_of(match) -> int:
    return pending_of(match).get("zone", 0)


def stamp_turn(match, state: dict) -> None:
    """Record when the current waiting state began — feeds the auto-roll timer."""
    state["stamp"] = {"turn": match["turn"], "at": db.now()}


def stale_since(state: dict, match) -> int | None:
    """Seconds the match has waited on the same turn — None if unknown/mismatched."""
    stamp = state.get("stamp") or {}
    if not stamp or stamp.get("turn") != match["turn"]:
        return None
    return max(0, db.now() - int(stamp.get("at", 0)))


def fresh_state() -> dict:
    return {
        "zone": 0,
        "last_pass": None,
        "beaten": [],
        "chain": 0,
        "buffs": [],
        "used": [],
        "armed": {},
        "lines": {},
        "last_holder": None,
        "charges": {},
        "stamp": {},
    }


def line_of(row) -> int:
    role = role_of(row["char_key"]) if row["char_key"] else ""
    if any(k in role for k in ("Striker", "Forward", "Poacher")):
        return 0
    if any(k in role for k in ("Winger", "Wing", "Dribbler", "Midfielder")):
        return 1
    return 2


def legal_actions(match) -> list[str]:
    state = pending_of(match)
    piece = state.get("set_piece")
    if piece == "penalty":
        return ["penalty"]
    if piece == "freekick":
        return ["freekick", "cross"]
    pup = state.get("puppet")
    if pup and pup.get("stage") == "await_action":
        return [pup.get("action") or "dribble"]
    zone = state.get("zone", 0)
    out = ["pass"]
    if zone < ZONE_BOX:
        out.append("dribble")
    if zone >= ZONE_SHOOT:
        out.append("shoot")
    return out


def illegal_reason(action: str, zone: int) -> str | None:
    if action == "dribble" and zone >= ZONE_BOX:
        return "No room to dribble in the box — pass or shoot."
    if action == "shoot" and zone < ZONE_SHOOT:
        return "Too far out — work the ball up first."
    return None


def start(match_id: int) -> bool:
    if not db.kickoff(match_id):
        return False
    roster = db.roster(match_id)
    state = {**fresh_state(), "lines": initial_lines(roster)}
    reset_charges(state, roster)
    teams = [t for t in (1, 2) if any(r["team"] == t for r in roster)]
    opener_team = None
    if teams:
        last = db.last_kickoff_team(db.match(match_id)["chat_id"])
        if last is None:
            opener_team = random.choice(teams)
        elif last in teams:
            others = [t for t in teams if t != last]
            opener_team = random.choice(others) if others else last
        else:
            opener_team = random.choice(teams)
    deep = initial_lines(roster)
    opener = None
    if opener_team is not None:
        mates = [r for r in roster if r["team"] == opener_team]
        opener = min(mates, key=lambda r: (-deep.get(r["slot"], line_of(r)), r["slot"]))
    db.update_match(
        match_id,
        phase="play",
        turn=1,
        holder=opener["slot"] if opener else None,
        pending=json.dumps(state),
    )
    if opener:
        side = "BLUE" if opener["team"] == 1 else "RED"
        tag = "kickoff:blue" if opener["team"] == 1 else "kickoff:red"
        db.log_event(match_id, f"🟢 [{tag}] Kickoff — <b>{opener['name']}</b> starts from the back for {side}.")
        db.update_match(match_id, pending=json.dumps({**state, "stamp": {"turn": 1, "at": db.now()}}))
    return True


def reset_charges(state: dict, roster: list) -> None:
    charges: dict[str, int] = {}
    kits = kits_by_user(roster)
    for row in roster:
        if row["user_id"] is None:
            continue
        for ab in kits.get(row["user_id"], []):
            if ab.id not in charges:
                charges[ab.id] = abilities.PASSIVE_CHARGES if ab.kind == "passive" else 1
    state["charges"] = charges


FORMATION = {
    1: [2],
    2: [1, 2],
    3: [0, 1, 2],
    4: [0, 1, 1, 2],
    5: [0, 0, 1, 1, 2],
}
LANE_NAME = ("Forward", "Mid", "Back")


def initial_lines(roster: list) -> dict:
    lines = {}
    for team in (1, 2):
        mates = [r for r in roster if r["team"] == team]
        if not mates:
            continue
        lanes = sorted(FORMATION[len(mates)], reverse=True)
        pool = sorted(mates, key=lambda r: (line_of(r), r["slot"]))
        for lane in lanes:
            pool.sort(key=lambda r: (abs(line_of(r) - lane), r["slot"]))
            lines[pool.pop(0)["slot"]] = lane
    return lines


def rotate_lines_after_goal(lines: dict, roster: list) -> dict:
    """Volleyball-style rotation after a goal: within each team the position
    values shift one step — the back line steps forward, the top line wraps
    around. Lane multiset per team is preserved, keeper is never a slot here
    (the keeper is the AI, every roster slot is a field player)."""
    lines = {int(k): v for k, v in (lines or {}).items()}
    for team in (1, 2):
        mates = [r for r in roster if r["team"] == team]
        if len(mates) < 2:
            continue
        mates.sort(key=lambda r: (lines.get(r["slot"], line_of(r)), r["slot"]))
        vals = [lines.get(r["slot"], line_of(r)) for r in mates]
        rotated = [vals[-1]] + vals[:-1]  # defender → one step forward, top → back
        for r, lane in zip(mates, rotated):
            lines[r["slot"]] = lane
    return lines


def shift_lines(lines: dict, roster: list, holder_team: int) -> dict:
    lines = {int(k): v for k, v in (lines or {}).items()}
    out = {}
    for r in roster:
        lane = lines.get(r["slot"], line_of(r))
        if r["team"] == holder_team:
            out[r["slot"]] = max(0, lane - 1)
        else:
            out[r["slot"]] = min(2, lane + 1)
    return out


def _drop_auto_armed(state: dict) -> None:
    """An auto-armed passive that never fired goes back to the pool."""
    tracked = state.pop("auto_armed", {})
    armed = state.get("armed", {})
    for slot, aid in tracked.items():
        if armed.get(slot) == aid:
            armed.pop(slot, None)


def bound_active(ctx: dict) -> bool:
    """Bound condition: the owner's Bound partner is on the SAME team in this
    match. Position in the rotation is irrelevant — both present = works.
    A one-way bound (BUFF) fails is_bound_pair → neither side activates.
    TEST SEASON: BOUND_ENABLED is False → Bound never activates."""
    if not BOUND_ENABLED:
        return False
    row = ctx.get("self")
    roster = ctx.get("roster") or []
    if row is None:
        return False
    try:
        uid = row["user_id"]
    except (KeyError, IndexError, TypeError):
        return False
    if uid is None:
        return False
    partner_char = db.get_bound(uid)
    if not partner_char:
        return False
    mate = next(
        (
            r for r in roster
            if r["user_id"] is not None and r["user_id"] != uid
            and r["char_key"] == partner_char and r["team"] == row["team"]
        ),
        None,
    )
    if mate is None:
        return False
    return bool(db.is_bound_pair(uid, mate["user_id"], roster))


def bound_bonus(ab, ctx: dict, val: int) -> int:
    """Numeric Bound abilities scale with the purchased tier: +(tier - 1)."""
    if not ab.bound or not val:
        return val
    try:
        uid = ctx["self"]["user_id"]
    except (KeyError, IndexError, TypeError):
        return val
    if uid is None:
        return val
    return val + max(0, db.get_bound_tier(uid) - 1)


def _gated(ab, ctx) -> bool:
    if ab.bound and not bound_active(ctx):
        return False
    if ab.when is None:
        return True
    try:
        return bool(ab.when(ctx))
    except Exception:
        return False


def grant_streak(state: dict, receiver_slot: int, amount: int, src_id: str,
                 kind: str = "streak", scope: str | None = None) -> None:
    """Taha's duration rules for persistent buffs.
    kind='streak' → granted mid-match; lives until THAT holder scores.
    kind='reward' → granted on a goal; lives until the next goal (any side).
    scope=None applies to every action, otherwise only the named action.
    Unlike state['buffs'] these survive turnovers."""
    state.setdefault("streaks", []).append(
        {"slot": receiver_slot, "amt": amount, "src": src_id,
         "kind": kind, "scope": scope}
    )


def open_duel(match_id: int, action: str, target_slot: int | None) -> dict:
    match = db.match(match_id)
    roster = db.roster(match_id)
    by_slot = {r["slot"]: r for r in roster}
    actor = by_slot.get(match["holder"])
    state = pending_of(match)
    zone = state.get("zone", 0)

    if actor is None:
        return {"error": "No one has the ball."}
    if action not in ACTION_STAT:
        return {"error": "Invalid action."}

    set_piece = state.get("set_piece")
    if set_piece and action != set_piece and action != "cross":
        return {"error": f"You must take the {ACTION_NAME[set_piece]}."}
    if action == "cross" and set_piece != "freekick":
        return {"error": "You can only cross from a free kick."}
    pup = state.get("puppet")
    if pup and pup.get("stage") == "await_action" and actor["slot"] == pup.get("mate") \
            and action != (pup.get("action") or "dribble"):
        return {"error": "Puppet Pull forces the dribble."}
    if not set_piece:
        if action in SET_PIECES or action == "cross":
            return {"error": "No set piece for you."}
        blocked = illegal_reason(action, zone)
        if blocked:
            return {"error": blocked}

    target = None
    if action in ("pass", "cross"):
        target = by_slot.get(target_slot)
        if target is None or target["team"] != actor["team"] or target["slot"] == actor["slot"]:
            return {"error": "Pick a teammate to receive it."}

    kits = abilities.kits_by_user(roster)
    att_kit = abilities.kit_of(kits, actor)
    beaten = state.get("beaten", [])
    direct_piece = set_piece and action != "cross"
    wall: list[int] = []
    if direct_piece:
        defender = None
    elif action == "shoot":
        wall = [
            r["slot"] for r in sorted(
                (r for r in roster if r["team"] != actor["team"] and r["slot"] not in beaten),
                key=lambda r: (-slot_stats(r)["meta"], r["slot"]),
            )
        ]
        defender = by_slot.get(wall[0]) if wall else None
    else:
        defender = marker(roster, actor["team"], beaten)

    ctx_att = abilities.build_ctx(match, roster, actor, defender, action, zone, state)
    notes: list[str] = []
    state["notes"] = notes

    # --- passives arm themselves (skipped entirely when PASSIVES_MANUAL)
    auto_slot = str(actor["slot"])
    if auto_slot not in state.get("armed", {}):
        for _ab in att_kit:
            if (
                _ab.kind == "passive"
                and not PASSIVES_MANUAL                     # manual: player taps the button
                and _ab.id not in state.get("no_auto", [])
                and abilities.usable(state, _ab)
                and _gated(_ab, ctx_att)
            ):
                abilities.arm(state, actor["slot"], _ab)
                state.setdefault("auto_armed", {})[str(actor["slot"])] = _ab.id
                break

    duel = {
        "action": action,
        "target": target["slot"] if target else None,
        "actor": actor["slot"],
        "defender": defender["slot"] if defender else None,
        "att_power": max(1, slot_stats(actor)[ACTION_STAT[action]]),
        "def_power": max(1, slot_stats(defender)["meta"]) if defender else 0,
        "wall": wall,
        "gk_power": KEEPER_POWER if (action in KEEPER_ACTIONS or action == "penalty") else 0,
        "att_boosts": [],
        "def_boosts": [],
        "att_floor": 0,
        "def_floor": 0,
        "zone_extra": 0,
        "auto": None,
        "pen_edge_passive": 0,
        "att_die": None,
        "def_die": None,
        "gk_die": None,
    }

    no_dice = defender is None and action in ("pass", "dribble")
    if no_dice:
        duel["no_dice"] = True

    # --- armed skill / passive of the attacker (manual activation) ------------
    armed = None if no_dice else abilities.peek_armed(state, actor["slot"])

    def _stash_goal(ab) -> None:
        """Remember this passive's goal payout — score_goal() pays it at the
        next goal by the owner's team, then forgets it."""
        if ab.goal_self or ab.goal_mate:
            state["pending_goal"] = {"owner": actor["slot"], "src": ab.id,
                                     "self_amt": ab.goal_self, "mate_amt": ab.goal_mate}

    if armed is not None and _gated(armed, ctx_att):
        if armed.auto == "win":
            abilities.spend_armed(state, actor["slot"])
            _stash_goal(armed)
            duel["auto"] = {"t": "win", "slot": actor["slot"], "aid": armed.id}
            duel["zone_extra"] = armed.zone_extra
            if armed.puppet and action == "pass" and duel.get("target") is not None:
                duel["puppet"] = {"rin": actor["slot"], "mate": duel["target"], "aid": armed.id}
            abilities.note(state, actor["name"], armed, icon=abilities.icon_for(armed))
        elif armed.bluff:
            abilities.spend_armed(state, actor["slot"])
            _stash_goal(armed)
            if duel.get("defender") is not None:
                # three dice, one of them called real — the defender must name it
                duel["bluff"] = {"real": random.randint(1, 3),
                                 "picker": duel["defender"],
                                 "src": armed.name, "aid": armed.id}
            else:
                duel["auto"] = {"t": "win", "slot": actor["slot"], "aid": armed.id}
            abilities.note(state, actor["name"], armed, icon=abilities.icon_for(armed))
        elif armed.gamble:
            abilities.spend_armed(state, actor["slot"])
            _stash_goal(armed)
            duel["gamble"] = True
            duel["gamble_min"] = armed.gamble_min
            duel["gamble_aid"] = armed.id
            duel["att_power"] += armed.att(ctx_att) if armed.att else 0
            abilities.note(state, actor["name"], armed, icon=abilities.icon_for(armed))
        else:
            val = 0
            if armed.att is not None:
                try:
                    val = armed.att(ctx_att) or 0
                except Exception:
                    val = 0
                val = bound_bonus(armed, ctx_att, val)
            if val or armed.save_self or armed.die_floor or armed.tie_win:
                abilities.spend_armed(state, actor["slot"])
                _stash_goal(armed)
                if val:
                    val = bound_bonus(armed, ctx_att, val)
                    duel["att_power"] += val
                    duel["att_boosts"].append((armed.name, val))
                # resolve() pays out `beats` AFTER the move is judged (and after
                # any goal it scored) — stash it so the spent charge still counts.
                if armed.beats and action in ("dribble", "shoot"):
                    state["pending_beats"] = {"amt": armed.beats, "src": armed.id}
                # "از بین یک الی N نفر": a threaded shot faces at most N of the
                # wall — he slips past the rest, who are tagged for the `beats`
                # payout instead of being rolled. A carry/pass picks its count at
                # resolve() from the attack die (1..N).
                if armed.through:
                    if action == "shoot" and duel.get("wall"):
                        _tw = list(duel["wall"])
                        duel["wall"] = _tw[:armed.through]
                        duel["through_extra"] = _tw[armed.through:]
                    else:
                        duel["through"] = armed.through
                if armed.sure_goal:
                    # he already read the field: nothing between him and goal
                    duel["auto"] = {"t": "win", "slot": actor["slot"], "aid": armed.id}
                    duel["sure_goal"] = True
                # Sae / Charles carry an attack bonus AND a receiver buff. The
                # bonus lands here and burns the charge, so the receiver buff
                # would find nothing in resolve() — stash it for the completed pass.
                if armed.pass_buff and action in ("pass", "cross") and duel.get("target") is not None:
                    state["pending_buff"] = {"amt": armed.pass_buff, "src": armed.id,
                                             "target": duel["target"]}
                if armed.gk_down:
                    duel["gk_down"] = armed.gk_down
                if armed.save_margin:
                    duel["save_margin"] = armed.save_margin
                if armed.tie_win:
                    duel["tie_win"] = True
                if armed.save_self:
                    duel["save_self"] = True
                if armed.die_floor:
                    duel["att_floor"] = armed.die_floor
                abilities.note(state, actor["name"], armed, icon=abilities.icon_for(armed))
            if action == "pass" and armed.pass_advance:
                duel["ghost_pass"] = True
                abilities.note(state, actor["name"], armed, "the ball can't be cut out", icon="➡️")

    kept_buffs = []
    for b in state.get("buffs", []):
        if b["slot"] == actor["slot"]:
            duel["att_power"] += b["amt"]
            duel["att_boosts"].append(("✨buff", b["amt"]))
            src = abilities.get(b["src"])
            if src:
                abilities.note(state, actor["name"], src, f"boosted +{b['amt']} by {b['from']}", icon="✨")
        else:
            kept_buffs.append(b)
    state["buffs"] = kept_buffs

    # persistent streaks — survive turnovers, filtered by scope
    for b in state.get("streaks", []):
        if b.get("slot") == actor["slot"] and (b.get("scope") in (None, action)):
            _sab = abilities.get(b.get("src", ""))
            duel["att_power"] += b["amt"]
            duel["att_boosts"].append((_sab.name if _sab else "streak", b["amt"]))
            if _sab:
                abilities.note(state, actor["name"], _sab, f"streak +{b['amt']}", icon="\U0001f525")

    # --- defender: armed defensive skill/passive -------------------------------
    def _defender_arms(row, power_key: str, boost_key: str, floor_key: str) -> None:
        """Apply the row's armed defensive ability to the current duel stage."""
        ctx_def = abilities.build_ctx(match, roster, row, actor, action, zone, state)
        # persistent streaks — survive turnovers, filtered by scope
        for b in state.get("streaks", []):
            if b.get("slot") == row["slot"] and (b.get("scope") in (None, action)):
                _sab = abilities.get(b.get("src", ""))
                duel[power_key] += b["amt"]
                duel[boost_key].append((_sab.name if _sab else "streak", b["amt"]))
        if str(row["slot"]) not in state.get("armed", {}):
            for _ab in abilities.kit_of(kits, row):
                if (
                    _ab.kind == "passive"
                    and not PASSIVES_MANUAL                 # manual: player taps the button
                    and _ab.id not in state.get("no_auto", [])
                    and abilities.usable(state, _ab)
                    and _gated(_ab, ctx_def)
                ):
                    abilities.arm(state, row["slot"], _ab)
                    state.setdefault("auto_armed", {})[str(row["slot"])] = _ab.id
                    break
        d_armed = abilities.peek_armed(state, row["slot"])
        if d_armed is None or not _gated(d_armed, ctx_def):
            return
        if d_armed.auto == "stop":
            abilities.spend_armed(state, row["slot"])
            duel["auto"] = {"t": "stop", "slot": row["slot"], "aid": d_armed.id}
            abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))
        elif d_armed.dfd is not None:
            try:
                val = d_armed.dfd(ctx_def) or 0
            except Exception:
                val = 0
            val = bound_bonus(d_armed, ctx_def, val)
            if val:
                abilities.spend_armed(state, row["slot"])
                duel[power_key] += val
                duel[boost_key].append((d_armed.name, val))
                abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))
        else:
            if d_armed.die_floor:
                abilities.spend_armed(state, row["slot"])
                duel[floor_key] = d_armed.die_floor
                abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))

    if defender is not None:
        _defender_arms(defender, "def_power", "def_boosts", "def_floor")
    for w in wall[1:]:
        _defender_arms(by_slot[w], "def_power", "def_boosts", "def_floor")
        if isinstance(duel.get("auto"), dict) and duel["auto"].get("t") == "stop":
            duel["defender"] = by_slot[w]["slot"]
            break

    if action in KEEPER_ACTIONS or action == "penalty":
        aura = sum(
            ab.aura_gk
            for r in roster if r["team"] == defender_team(actor)
            for ab in abilities.kit_of(kits, r)
            if ab.kind == "passive" and ab.aura_gk
        )
        duel["gk_power"] += aura

    if action == "penalty":
        duel["pen_edge_passive"] = sum(
            ab.pen_edge for ab in att_kit if ab.kind == "passive" and ab.pen_edge
        )
        keeper_captain = team_captain(roster, defender_team(actor))
        duel["spotter"] = keeper_captain["slot"] if keeper_captain else None
        duel["att_spot"] = None
        duel["gk_spot"] = None

    state["duel"] = duel
    notes_out = state.pop("notes", [])
    with db.tx() as c:
        cur = c.execute(
            "UPDATE matches SET phase='duel', pending=? WHERE id=? AND phase='opening'",
            (json.dumps(state), match_id),
        )
        if cur.rowcount != 1:
            return {"error": "This turn was already taken."}
    return {
        "ok": True,
        "actor": actor,
        "defender": defender,
        "action": action,
        "zone": zone,
        "notes": notes_out,
        "unmarked": defender is None and action not in SET_PIECES and action != "cross",
        "duel": duel,
    }


def cancel_duel(match_id: int) -> None:
    match = db.match(match_id)
    state = pending_of(match)
    state.pop("duel", None)
    state.pop("notes", None)
    # an abandoned duel must not leave its payout behind for the next action
    state.pop("pending_buff", None)
    state.pop("pending_beats", None)
    state.pop("pending_goal", None)
    _drop_auto_armed(state)
    db.update_match(match_id, phase="play", pending=json.dumps(state))


def total(duel: dict, prefix: str) -> int | None:
    die = duel[f"{prefix}_die"]
    if die is None:
        return None
    floor = duel.get(f"{prefix}_floor", 0) if prefix in ("att", "def") else 0
    return max(die, floor) + duel[f"{prefix}_power"]


def past_defender(duel: dict, defender_slot: int | None = None) -> bool | None:
    auto = duel.get("auto")
    if auto:
        return auto["t"] == "win"
    if duel.get("gamble") and duel.get("att_die") is not None:
        die = duel["att_die"]
        gamble_min = duel.get("gamble_min", 0)
        if gamble_min and die < gamble_min:
            return False
        return True
    if defender_slot is None:
        defender_slot = duel.get("defender")
    if defender_slot is None:
        return True
    att, dfn = total(duel, "att"), total(duel, "def")
    if att is None or dfn is None:
        return None
    if att == dfn:
        return bool(duel.get("tie_win"))
    return att > dfn


def _roles(duel: dict) -> list[tuple[str, str, int | None]]:
    auto = duel.get("auto")
    if isinstance(auto, dict) and auto.get("t") == "stop":
        return []
    if duel["action"] == "penalty":
        roles = [("spot", "att_spot", duel["actor"])]
        if duel.get("spotter") is not None:
            roles.append(("spot_gk", "gk_spot", duel["spotter"]))
        return roles
    won_auto = isinstance(auto, dict) and auto.get("t") == "win"
    if won_auto:
        if duel["action"] in KEEPER_ACTIONS:
            return [("att", "att_die", duel["actor"]), ("gk", "gk_die", None)]
        return []
    if duel.get("no_dice"):
        return []
    roles = []
    _bl = duel.get("bluff")
    if _bl and duel.get("bluff_pick") is None and _bl.get("picker") is not None:
        roles.append(("bluff", "bluff_pick", _bl["picker"]))
    roles.append(("att", "att_die", duel["actor"]))
    wall = duel.get("wall") or []
    if duel["action"] == "shoot" and not duel.get("gamble"):
        for slot in wall:
            die = duel.get(f"die_{slot}")
            if die is None:
                roles.append(("def", f"die_{slot}", slot))
                break
            snapshot = {**duel, "defender": slot, "def_die": die}
            if past_defender(snapshot, slot) is not True:
                break
    elif duel["defender"] is not None and not duel.get("gamble") and not duel.get("ghost_pass"):
        roles.append(("def", "def_die", duel["defender"]))
    if duel["action"] in KEEPER_ACTIONS and _wall_cleared(duel) is True:
        roles.append(("gk", "gk_die", None))
    return roles


def _wall_cleared(duel: dict) -> bool | None:
    """True = every wall member beaten (keeper faces the shot); False = stopped; None = pending."""
    if duel.get("auto"):
        return duel["auto"]["t"] == "win"
    if duel.get("gamble"):
        die = duel.get("att_die")
        if die is None:
            return None
        return duel.get("gamble_min", 0) <= die
    wall = duel.get("wall") or []
    for slot in wall:
        die = duel.get(f"die_{slot}")
        if die is None:
            return None
        snapshot = {**duel, "defender": slot, "def_die": die}
        verdict = past_defender(snapshot, slot)
        if verdict is not True:
            return False
    return True


def _next_role(duel: dict) -> tuple[str, str, int | None] | None:
    for spec in _roles(duel):
        if duel.get(spec[1]) is None:
            return spec
    return None


def awaiting(match) -> dict | None:
    duel = pending_of(match).get("duel")
    if not duel:
        return None
    spec = _next_role(duel)
    if spec is None:
        return None
    role, _, slot = spec
    if role == "gk":
        return {"role": role, "slot": None, "name": KEEPER_NAME, "user_id": None, "duel": duel}
    row = next((r for r in db.roster(match["id"]) if r["slot"] == slot), None)
    if row is None:
        return None
    out = {"role": role, "slot": slot, "name": row["name"], "user_id": row["user_id"], "duel": duel}
    if role in ("spot", "spot_gk"):
        out["label"] = "Pick your corner" if role == "spot" else "Call the keeper's dive"
    if role == "bluff":
        out["label"] = "Which die did he call real?"
    return out


def ready(match) -> bool:
    duel = pending_of(match).get("duel")
    return bool(duel) and _next_role(duel) is None


def _claim(match_id: int, user_id: int, value, expect: tuple[str, ...]) -> dict:
    with db.tx() as c:
        row = c.execute("SELECT pending FROM matches WHERE id=? AND phase='duel'", (match_id,)).fetchone()
        if not row:
            return {"status": "closed"}
        state = json.loads(row["pending"] or "{}")
        duel = state.get("duel")
        if not duel:
            return {"status": "closed"}
        spec = _next_role(duel)
        if spec is None:
            return {"status": "closed"}
        role, key, slot = spec
        if role not in expect:
            return {"status": "keeper" if role == "gk" else "closed"}
        owner = c.execute(
            "SELECT name, user_id, team FROM match_players WHERE match_id=? AND slot=?", (match_id, slot)
        ).fetchone()
        if owner is None:
            return {"status": "closed"}
        if role == "spot_gk":
            caller = c.execute(
                "SELECT team FROM match_players WHERE match_id=? AND user_id=?", (match_id, user_id)
            ).fetchone()
            if caller is None or caller["team"] != owner["team"]:
                return {"status": "wrong", "name": owner["name"], "role": role}
        elif owner["user_id"] is not None and owner["user_id"] != user_id:
            return {"status": "wrong", "name": owner["name"], "role": role}
        duel[key] = value
        c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
        return {"status": "ok", "role": role, "name": owner["name"]}


def submit_die(match_id: int, user_id: int, value: int) -> dict:
    if not isinstance(value, int) or not 1 <= value <= DICE_FACES:
        return {"status": "invalid"}
    return _claim(match_id, user_id, value, ("att", "def"))


def submit_spot(match_id: int, user_id: int, target: str) -> dict:
    if target not in PENALTY_TARGETS:
        return {"status": "invalid"}
    return _claim(match_id, user_id, target, ("spot", "spot_gk"))


def submit_bluff(match_id: int, user_id: int, pick: int) -> dict:
    """Hugo's Phantom Call: the defender names which of the three dice is real.
    Call it right and the duel runs normally; call it wrong and there is no
    contest — his pass/shot lands ("گارانتی رد یا گل")."""
    if pick not in (1, 2, 3):
        return {"status": "invalid"}
    out = _claim(match_id, user_id, pick, ("bluff",))
    if out.get("status") != "ok":
        return out
    with db.tx() as c:
        row = c.execute("SELECT pending FROM matches WHERE id=? AND phase='duel'", (match_id,)).fetchone()
        if not row:
            return out
        state = json.loads(row["pending"] or "{}")
        duel = state.get("duel") or {}
        bl = duel.get("bluff") or {}
        if bl and duel.get("bluff_pick") is not None and duel["bluff_pick"] != bl.get("real"):
            duel["auto"] = {"t": "win", "slot": duel.get("actor"),
                            "aid": bl.get("aid"), "src": bl.get("src"),
                            "bluff_miss": True}
            c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
    return out


def record_die(match_id: int, role: str, value: int) -> bool:
    if not isinstance(value, int) or not 1 <= value <= DICE_FACES:
        return False
    with db.tx() as c:
        row = c.execute("SELECT pending FROM matches WHERE id=? AND phase='duel'", (match_id,)).fetchone()
        if not row:
            return False
        state = json.loads(row["pending"] or "{}")
        duel = state.get("duel")
        if not duel:
            return False
        spec = _next_role(duel)
        if spec is None or spec[0] != role:
            return False
        duel[spec[1]] = value
        c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
        return True


def arm_skill(match_id: int, user_id: int, ability_id: str) -> dict:
    """Player presses the ⚡ button: arm (or cancel-arm) a ready skill or passive."""
    ab = abilities.get(ability_id)
    if ab is None:
        return {"status": "invalid"}
    match = db.match(match_id)
    if not match or match["status"] != "live" or match["phase"] not in ("play", "duel"):
        return {"status": "closed"}
    roster = db.roster(match_id)
    me = next((r for r in roster if r["user_id"] == user_id), None)
    if me is None or me["char_key"] != ab.char:
        return {"status": "foreign"}
    if ability_id not in abilities.owned_ids(user_id, ab.char):
        return {"status": "locked", "name": ab.name}
    holder_slot = match["holder"]
    is_holder = holder_slot == me["slot"]
    with db.tx() as c:
        row = c.execute(
            "SELECT pending FROM matches WHERE id=? AND status='live' AND phase IN ('play','duel')",
            (match_id,),
        ).fetchone()
        if not row:
            return {"status": "closed"}
        state = json.loads(row["pending"] or "{}")
        if not abilities.usable(state, ab):
            return {"status": "spent"}
        if ab.kind == "skill":
            # skill slots: how many DIFFERENT skills a player may use per match
            slots = db.get_skill_slots(user_id)
            used_skills = 0
            for u in state.get("used", []):
                g = abilities.get(u)
                if g is not None and g.kind == "skill" and g.char == ab.char:
                    used_skills += 1
            if used_skills >= slots:
                return {"status": "spent", "name": ab.name}
        if match["phase"] == "duel" and not is_defensive(ab):
            return {"status": "notturn", "name": ab.name}
        current = state.setdefault("armed", {})
        mine_key = str(me["slot"])
        state.get("auto_armed", {}).pop(mine_key, None)
        if current.get(mine_key) == ability_id:
            current.pop(mine_key, None)
            if ab.kind == "passive":
                paused = state.setdefault("no_auto", [])
                if ability_id not in paused:
                    paused.append(ability_id)
            c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
            return {"status": "disarmed", "name": ab.name}
        if mine_key in current:
            other = abilities.get(current[mine_key])
            if other is not None and other.kind == "passive":
                # an auto-armed passive yields to whatever the player presses
                current.pop(mine_key, None)
            else:
                return {"status": "swap", "name": other.name if other else "?"}
        if not is_holder and not is_defensive(ab):
            return {"status": "notturn", "name": ab.name}
        current[mine_key] = ability_id
        c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
        return {"status": "armed", "name": ab.name, "kind": ab.kind}


def is_defensive(ab) -> bool:
    return ab.auto == "stop" or ab.punch_to_self or ab.dfd is not None or ab.first_free


def _snapshot(duel: dict, actor, defender, zone: int) -> dict:
    wall = duel.get("wall") or []
    return {
        "actor": actor,
        "defender": defender,
        "action": duel["action"],
        "zone": zone,
        "att_die": duel["att_die"],
        "att_power": duel["att_power"],
        "att_total": total(duel, "att"),
        "att_boosts": duel.get("att_boosts", []),
        "def_die": duel["def_die"],
        "def_power": duel["def_power"],
        "def_total": total(duel, "def"),
        "def_boosts": duel.get("def_boosts", []),
        "wall_rolls": [
            {"slot": slot, "die": duel.get(f"die_{slot}")}
            for slot in wall
            if duel.get(f"die_{slot}") is not None
        ],
        "gk_die": duel["gk_die"],
        "gk_power": duel["gk_power"],
        "gk_total": total(duel, "gk"),
        "vs_keeper": duel["action"] in KEEPER_ACTIONS or duel["action"] == "penalty",
    }


def resolve(match_id: int) -> dict | None:
    with db.tx() as c:
        row = c.execute("SELECT pending, phase FROM matches WHERE id=?", (match_id,)).fetchone()
        if not row or row["phase"] != "duel":
            return None
        state = json.loads(row["pending"] or "{}")
        duel = state.get("duel")
        if not duel or _next_role(duel) is not None:
            return None
        c.execute("UPDATE matches SET phase='resolving' WHERE id=?", (match_id,))

    match = db.match(match_id)
    roster = db.roster(match_id)
    by_slot = {r["slot"]: r for r in roster}
    zone = state.get("zone", 0)

    actor = by_slot[duel["actor"]]
    defender = by_slot.get(duel["defender"]) if duel["defender"] is not None else None
    action = duel["action"]
    was_set_piece = action in SET_PIECES
    # Stashed by open_duel() when the passive burns its charge there (attack
    # bonus + receiver buff in one ability, e.g. Sae / Charles). Popped right
    # away so an incomplete pass drops it instead of leaking to a later action.
    pbuff = state.pop("pending_buff", None)

    _seen_boosts = {(b[0], b[1]) for b in duel.get("def_boosts", [])}
    for slot in ([duel["defender"]] if duel.get("defender") is not None else []) + (duel.get("wall") or []):
        row = by_slot.get(slot)
        if row is None:
            continue
        d_armed = abilities.peek_armed(state, slot)
        if d_armed is None or d_armed.dfd is None or d_armed.gamble:
            continue
        ctx_def = abilities.build_ctx(match, roster, row, actor, action, zone, state)
        try:
            val = d_armed.dfd(ctx_def) or 0
        except Exception:
            val = 0
        if val and (d_armed.name, val) not in _seen_boosts:
            abilities.spend_armed(state, slot)
            duel["def_power"] += val
            duel["def_boosts"].append((d_armed.name, val))
            abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))

    out = _snapshot(duel, actor, defender, zone)
    if action in ("pass", "cross"):
        out["target"] = by_slot.get(duel["target"])
    if action == "penalty":
        out["att_spot"] = duel["att_spot"]
        out["gk_spot"] = duel["gk_spot"]
        out["spotter"] = by_slot.get(duel.get("spotter"))

    state["notes"] = state.get("notes", [])
    notes = list(state["notes"])
    state["notes"] = []

    auto = duel.get("auto")
    gamble_win = False
    gamble_n = 0
    if duel.get("gamble") and defender is not None and auto is None:
        die = duel.get("att_die") or 1
        gamble_min = duel.get("gamble_min", 0)
        if gamble_min and die < gamble_min:
            out["gamble_backfire"] = True
            duel["auto"] = {"t": "stop", "slot": defender["slot"], "aid": duel.get("gamble_aid")}
            ab = abilities.get(duel.get("gamble_aid"))
            if ab:
                abilities.note(state, actor["name"], ab, "backfired — the gamble collapses", icon="💀")
        elif action in ("pass", "cross"):
            gamble_win = True
        else:
            gamble_n = max(1, die)
            gamble_win = True
            duel["auto"] = {"t": "win", "slot": actor["slot"], "aid": None, "gamble": gamble_n}
    deadlock = False
    wall = duel.get("wall") or []
    if action == "shoot" and duel.get("auto") is None and not duel.get("gamble"):
        cleared = True
        for slot in wall:
            die = duel.get(f"die_{slot}")
            snapshot = {**duel, "defender": slot, "def_die": die}
            verdict = past_defender(snapshot, slot)
            if verdict is None:
                if duel.get("tie_win"):
                    continue
                deadlock = True
                break
            if verdict is not True:
                cleared = False
                break
    else:
        cleared = past_defender(duel)
        if duel.get("no_dice"):
            cleared = True
        elif defender is not None and auto is None and cleared is not None:
            deadlock = out["att_total"] == out["def_total"] and not duel.get("tie_win")
    if duel.get("ghost_pass") and auto is None:
        cleared = True
    beaten = list(state.get("beaten", []))
    beaten_before = set(beaten)   # who was already down BEFORE this move
    wall = duel.get("wall") or []
    wall_beaten = []
    if action == "shoot":
        for slot in wall:
            die = duel.get(f"die_{slot}")
            if die is None:
                break
            snapshot = {**duel, "defender": slot, "def_die": die}
            if past_defender(snapshot, slot) is True:
                wall_beaten.append(slot)
            else:
                break
    out["unmarked"] = defender is None and not was_set_piece and action != "cross"

    db.bump_slot(match_id, actor["slot"], actions=1)
    state.pop("set_piece", None)
    new_holder = actor["slot"]
    kept_possession = False

    def turnover(slot: int) -> int:
        beaten.clear()
        state["zone"] = 0
        state["last_pass"] = None
        state["chain"] = 0
        state["buffs"] = []
        if actor is not None:
            beaten.append(actor["slot"])
        for w in wall_beaten:
            if w not in beaten:
                beaten.append(w)
        if state.get("last_holder") != slot:
            holder_team = by_slot[slot]["team"] if slot in by_slot else actor["team"]
            state["lines"] = shift_lines(state.get("lines", {}), roster, holder_team)
            state["last_holder"] = slot
        return slot

    def award_piece(reason: str) -> None:
        piece = "penalty" if zone >= ZONE_BOX else "freekick"
        state["set_piece"] = piece
        state["last_pass"] = None
        beaten.clear()
        state["chain"] = 0
        out["outcome"] = "foul"
        out["set_piece"] = piece
        out["reason"] = reason

    def score_goal() -> None:
        nonlocal new_holder
        out["outcome"] = "goal"
        # Taha's duration rules: every goal reward expires at the NEXT goal;
        # a mid-match streak expires when its own holder scores.
        state["streaks"] = [
            s for s in state.get("streaks", [])
            if s.get("kind") != "reward" and s.get("slot") != actor["slot"]
        ]
        # Passive goal payout (Taha's "اگ گل شد ... میگیره"): owed to the owner
        # once his team scores. Granted AFTER the sweep so it survives this goal
        # and the next one wipes it. The pending is dropped either way.
        pg = state.pop("pending_goal", None)
        if pg:
            _owner = by_slot.get(pg.get("owner"))
            if _owner is not None and _owner["team"] == actor["team"]:
                if pg.get("self_amt"):
                    grant_streak(state, pg["owner"], pg["self_amt"],
                                 pg.get("src", ""), kind="reward")
                if pg.get("mate_amt"):
                    _mate = (state.get("last_pass")
                             if pg.get("owner") == actor["slot"] else actor["slot"])
                    if _mate is not None and _mate != pg.get("owner"):
                        grant_streak(state, _mate, pg["mate_amt"],
                                     pg.get("src", ""), kind="reward")
        db.bump_slot(match_id, actor["slot"], goals=1)
        assist_slot = state.get("last_pass")
        if assist_slot is not None and assist_slot != actor["slot"]:
            assister = by_slot.get(assist_slot)
            if assister is not None and assister["team"] == actor["team"]:
                db.bump_slot(match_id, assist_slot, assists=1)
                out["assister"] = assister
        # PUPPET window: Rin's own goal pays +1 to him and the helper
        pup = state.get("puppet")
        if pup and pup.get("stage") == "done" and actor["slot"] == pup.get("rin"):
            grant_streak(state, actor["slot"], 1, pup.get("aid", "rin_p1"),
                         kind="reward", scope=None)
            if assist_slot is not None and assist_slot != actor["slot"]:
                grant_streak(state, assist_slot, 1, pup.get("aid", "rin_p1"),
                             kind="reward", scope=None)
            pup["stage"] = "spent"
        field = "score1" if actor["team"] == 1 else "score2"
        db.update_match(match_id, **{field: match[field] + 1})
        conceded = [r for r in roster if r["team"] != actor["team"]]
        new_holder = turnover(random.choice(conceded)["slot"] if conceded else actor["slot"])
        # volleyball-style rotation: after every goal the positions turn over —
        # whoever sat in the back line steps one step forward.
        state["lines"] = rotate_lines_after_goal(state.get("lines", {}), roster)
        if beaten and beaten[-1] == actor["slot"] and actor["slot"] not in wall_beaten:
            beaten.pop()

    def grant_buff(receiver_slot: int, amount: int, ab) -> None:
        state.setdefault("buffs", []).append(
            {"slot": receiver_slot, "amt": amount, "src": ab.id, "from": actor["name"]}
        )
        abilities.note(state, actor["name"], ab, f"receiver +{amount}", icon="✨")

    def puppet_take(next_zone: int, keep_outcome: bool = False) -> None:
        """Rin's Puppet Pull: after the forced receiver dribble (or straight
        away when there is no room for it) Rin snatches the ball back —
        guaranteed, counted like beating a defender — and the confirmed
        bonuses land as goal-duration streaks."""
        nonlocal new_holder, kept_possession
        pup = state.get("puppet")
        if not pup or pup.get("stage") != "await_action":
            return
        rin_row = by_slot.get(pup.get("rin"))
        if rin_row is None:
            return
        if not keep_outcome:
            out["outcome"] = "dribble_ok"
        out.pop("set_piece", None)
        state.pop("set_piece", None)
        if defender is not None and defender["slot"] not in beaten:
            beaten.append(defender["slot"])
            out["beat"] = defender
        state["zone"] = next_zone
        state["last_pass"] = None
        state["chain"] = state.get("chain", 0) + 1
        new_holder = rin_row["slot"]
        kept_possession = True
        grant_streak(state, rin_row["slot"], 2, pup.get("aid", "rin_p1"),
                     kind="streak", scope="shoot")
        if pup.get("mate") is not None:
            grant_streak(state, pup["mate"], 1, pup.get("aid", "rin_p1"),
                         kind="streak", scope=None)
        out["puppet_take"] = rin_row
        _pab = abilities.get(pup.get("aid", ""))
        if _pab:
            abilities.note(state, rin_row["name"], _pab,
                           "Puppet Pull \u2014 takes it back", icon="\U0001f3ad")
        pup["stage"] = "done"

    def keeper_restart(catch: bool) -> None:
        nonlocal new_holder
        out["outcome"] = "saved"
        out["keeper_dist"] = "catch" if catch else "punch"
        receiver = None
        if not catch:
            self_ab = abilities.peek_armed(state, actor["slot"])
            if (self_ab is not None and self_ab.save_self) or duel.get("save_self"):
                if self_ab is not None and self_ab.save_self:
                    abilities.spend_armed(state, actor["slot"])
                receiver = actor
            else:
                for r in roster:
                    if r["team"] == defender_team(actor):
                        d_ab = abilities.peek_armed(state, r["slot"])
                        if d_ab is not None and d_ab.punch_to_self:
                            abilities.spend_armed(state, r["slot"])
                            receiver = r
                            abilities.note(state, r["name"], d_ab, "loose ball claimed")
                            break
        if receiver is None and catch:
            mates = [r for r in roster if r["team"] == defender_team(actor)]
            receiver = random.choice(mates) if mates else actor
        if receiver is None:
            receiver = loose_ball_to(roster, actor, beaten)
        out["receiver"] = receiver
        new_holder = turnover(receiver["slot"])

    if auto is not None and auto["t"] == "stop":
        stopper = by_slot[auto["slot"]]
        out["outcome"] = {"pass": "intercepted", "cross": "intercepted", "dribble": "tackled"}.get(action, "blocked")
        out["stopped_by_skill"] = stopper
        db.bump_slot(match_id, stopper["slot"], stops=1)
        new_holder = turnover(stopper["slot"])
    elif deadlock:
        award_piece("deadlock")
    elif not cleared:
        lost_ab = abilities.peek_armed(state, actor["slot"])
        if lost_ab is not None and lost_ab.on_lost == "foul":
            abilities.spend_armed(state, actor["slot"])
            abilities.note(state, actor["name"], lost_ab, "won the free kick")
            award_piece("drawn")
        elif action == "dribble" and lost_ab is not None and lost_ab.tackle_keep:
            abilities.spend_armed(state, actor["slot"])
            abilities.note(state, actor["name"], lost_ab, "escaped the tackle")
            out["outcome"] = "dribble_ok"
            beaten.append(defender["slot"])
            out["beat"] = defender
            state["zone"] = min(ZONE_BOX, zone + 1)
            state["last_pass"] = None
            state["chain"] = state.get("chain", 0) + 1
            kept_possession = True
        else:
            out["outcome"] = "intercepted" if action in ("pass", "cross") else "blocked"
            if lost_ab is not None and lost_ab.first_free and not state.get("first_free_used"):
                abilities.spend_armed(state, actor["slot"])
                state["first_free_used"] = True
                abilities.note(state, actor["name"], lost_ab, "the loss doesn't count — one more try")
                out["first_free"] = True
                state["beaten"] = beaten
                out["notes"] = notes + state.pop("notes", [])
                state.pop("duel", None)
                db.update_match(match_id, phase="play", pending=json.dumps(state))
                return out
            stopper = defender
            if action == "shoot":
                for slot in duel.get("wall") or []:
                    die = duel.get(f"die_{slot}")
                    if die is None:
                        break
                    snapshot = {**duel, "defender": slot, "def_die": die}
                    if past_defender(snapshot, slot) is not True:
                        stopper = by_slot[slot]
                        break
            db.bump_slot(match_id, stopper["slot"], stops=1)
            new_holder = turnover(stopper["slot"])
    elif action == "penalty":
        # No dice: the corner call decides it. A read corner is a guaranteed stop,
        # a missed corner is a guaranteed goal — abilities only push the keeper off
        # the shooter's corner, they never break the read.
        gk_spot = out["gk_spot"]
        pen_ab = abilities.peek_armed(state, actor["slot"])
        autoscore = False
        if pen_ab is not None and (pen_ab.pen_edge or pen_ab.pen_autoscore):
            abilities.spend_armed(state, actor["slot"])
            autoscore = True
            abilities.note(state, actor["name"], pen_ab, "keeper is sent the wrong way")
        if autoscore and gk_spot == out["att_spot"]:
            options = [t for t in PENALTY_TARGETS if t != out["att_spot"]]
            gk_spot = random.choice(options)
            out["gk_spot"] = gk_spot
            out["autoscore"] = True
        if out["att_spot"] != gk_spot:
            score_goal()
        else:
            keeper_restart(catch=True)
            out["nerve"] = "read"
    elif action in KEEPER_ACTIONS:
        for slot in wall_beaten:
            if slot not in beaten:
                beaten.append(slot)
        shot_ab = abilities.peek_armed(state, actor["slot"])
        down = duel.get("gk_down", 0)
        margin = duel.get("save_margin", 0)
        tie = bool(duel.get("tie_win"))
        if shot_ab is not None and (shot_ab.gk_down or shot_ab.save_margin or shot_ab.tie_win):
            abilities.spend_armed(state, actor["slot"])
            down = down or shot_ab.gk_down
            margin = margin or shot_ab.save_margin
            tie = tie or bool(shot_ab.tie_win)
            abilities.note(state, actor["name"], shot_ab, "ultimate strike" if down >= 3 else "clinical finish")
        eff_gk_total = total(duel, "gk") - down
        if down:
            out["gk_total_eff"] = eff_gk_total
        att_t = out["att_total"]
        won = att_t > eff_gk_total
        if not won and tie and att_t == eff_gk_total:
            won = True
            out["tie_win"] = True
        if not won and margin and att_t >= eff_gk_total - margin:
            won = True
            out["margin_goal"] = margin
        if duel.get("sure_goal"):
            won = True
            out["sure_goal"] = True
        if won:
            score_goal()
        else:
            keeper_restart(catch=duel["gk_die"] >= KEEPER_CATCH_ROLL)
    else:
        for slot in wall_beaten:
            if slot not in beaten:
                beaten.append(slot)
        if defender is not None and defender["slot"] not in wall_beaten:
            beaten.append(defender["slot"])
            out["beat"] = defender
        if gamble_win and gamble_n > 1:
            free_defs = [
                r for r in roster
                if r["team"] != actor["team"] and r["slot"] not in beaten
            ][: gamble_n - 1]
            for d in free_defs:
                beaten.append(d["slot"])
            out["gamble_beaten"] = min(gamble_n, len(beaten))
        state["zone"] = min(ZONE_BOX, zone + 1 + duel.get("zone_extra", 0))
        if action == "pass":
            out["outcome"] = "pass_ok"
            out["walked"] = bool(duel.get("no_dice"))
            state["last_pass"] = actor["slot"]
            new_holder = duel["target"]
            puppet_mark = duel.get("puppet")
            if puppet_mark:
                state["puppet"] = dict(puppet_mark, stage="await_action", action="dribble")
                if state.get("zone", 0) < ZONE_BOX:
                    _pab = abilities.get(puppet_mark.get("aid", ""))
                    if _pab:
                        abilities.note(state, actor["name"], _pab, "Puppet Pull", icon="\U0001f3ad")
                else:
                    # no room for the forced dribble — the pull happens on the spot
                    puppet_take(state["zone"], keep_outcome=True)
            buff_ab = abilities.peek_armed(state, actor["slot"])
            if pbuff is not None:
                # charge already burned in open_duel — pay the stashed buff
                _pab = abilities.get(pbuff.get("src", ""))
                if _pab is not None:
                    grant_buff(pbuff["target"], bound_bonus(_pab, {"self": actor, "roster": roster}, pbuff["amt"]), _pab)
            elif buff_ab is not None and buff_ab.pass_buff:
                abilities.spend_armed(state, actor["slot"])
                grant_buff(duel["target"], bound_bonus(buff_ab, {"self": actor, "roster": roster}, buff_ab.pass_buff), buff_ab)
            if buff_ab is not None and buff_ab.pass_advance:
                abilities.spend_armed(state, actor["slot"])
                state["zone"] = min(ZONE_BOX, state["zone"] + buff_ab.pass_advance)
                out["pass_advanced"] = buff_ab.pass_advance
                abilities.note(state, actor["name"], buff_ab, f"receiver breaks forward +{buff_ab.pass_advance} zone", icon="➡️")
        elif action == "cross":
            out["outcome"] = "cross_ok"
            state["zone"] = ZONE_SHOOT
            state["last_pass"] = actor["slot"]
            new_holder = duel["target"]
            buff_ab = abilities.peek_armed(state, actor["slot"])
            if pbuff is not None:
                _pab = abilities.get(pbuff.get("src", ""))
                if _pab is not None:
                    grant_buff(pbuff["target"], bound_bonus(_pab, {"self": actor, "roster": roster}, pbuff["amt"]), _pab)
            elif buff_ab is not None and buff_ab.pass_buff:
                abilities.spend_armed(state, actor["slot"])
                grant_buff(duel["target"], bound_bonus(buff_ab, {"self": actor, "roster": roster}, buff_ab.pass_buff), buff_ab)
        else:
            out["outcome"] = "dribble_ok"
            out["walked"] = bool(duel.get("no_dice"))
            state["last_pass"] = None
        state["chain"] = state.get("chain", 0) + 1
        kept_possession = True

    # --- PUPPET: the forced dribble resolved — Rin takes it back, guaranteed
    if action == "dribble" and state.get("puppet", {}).get("stage") == "await_action" \
            and actor["slot"] == state["puppet"].get("mate"):
        puppet_take(min(ZONE_BOX, zone + 1))

    # --- "از بین یک الی N نفر" — leftovers of a threaded shot are already tagged
    # at open_duel; a carry/pass rolls its band NOW (attack die, capped by
    # `through`) and the extras join `beaten` so the debuff below reaches them.
    if out.get("outcome") in ("goal", "dribble_ok", "pass_ok"):
        _take = list(duel.get("through_extra") or [])
        _cap = int(duel.get("through") or 0)
        if _cap:
            _n = max(1, min(int(duel.get("att_die") or 1), _cap))
            _need = _n if action == "shoot" else _n - 1
            if _need > 0:
                _opp = [r["slot"] for r in roster
                        if r["team"] != actor["team"]
                        and r["slot"] not in beaten
                        and r["slot"] not in _take]
                _take += _opp[:_need]
        _added = [s for s in _take if s not in beaten]
        for _s in _added:
            beaten.append(_s)
        if _added:
            out["through_beaten"] = len(_added)

    # --- Emperor (Kaiser): everyone he shot past takes -1 until the next goal.
    # Paid out HERE — after any goal the shot just scored — so the debuff is
    # dealt on the goal and survives it (Taha: "تا گل بعدی", any goal clears it).
    pb = state.pop("pending_beats", None)
    if pb:
        _pb_ab = abilities.get(pb.get("src", ""))
        # everyone THIS move put on the floor — wall roll, marker, or the
        # "از بین N نفر" band. Already-beaten players keep their old tag.
        _targets = [s for s in beaten
                    if s not in beaten_before and s != actor["slot"]]
        for _slot in _targets:
            grant_streak(state, _slot, pb["amt"], pb.get("src", ""), kind="reward")
        if _pb_ab and _targets:
            abilities.note(state, actor["name"], _pb_ab,
                           f"{len(_targets)} beaten → {pb['amt']} until the next goal",
                           icon="👑")

    state["beaten"] = beaten
    out["beaten"] = beaten
    out["kept_possession"] = kept_possession
    out["notes"] = notes + state.pop("notes", [])

    _drop_auto_armed(state)
    state.pop("duel", None)
    turn = match["turn"] + 1
    db.update_match(match_id, turn=turn, holder=new_holder, phase="play", pending=json.dumps(state))
    out["turn"] = turn
    out["state"] = state
    return out


def duel_line(out: dict) -> str:
    if out["defender"] is None and not out.get("wall_rolls"):
        return ""
    att_boosts = out.get("att_boosts") or []
    def_boosts = out.get("def_boosts") or []
    att_parts = [f"{out['att_die']}"] + [f"⚡{n}" for _, n in att_boosts]
    att_sum = "+".join(att_parts) + f"+{out['att_power']}"
    att_total = f"{out['att_total']}" if out["att_total"] is not None else "?"
    if out.get("wall_rolls"):
        return f"<code>{att_sum}={att_total}</code> vs 🧱 <i>wall</i>"
    if out.get("def_die") is None:
        if out.get("att_die") is None:
            return ""
        return f"<code>{att_sum}={att_total}</code>"
    def_parts = [f"{out['def_die']}"] + [f"🛡{n}" for _, n in def_boosts]
    def_sum = "+".join(def_parts) + f"+{out['def_power']}"
    def_total = f"{out['def_total']}" if out["def_total"] is not None else "?"
    return (
        f"<code>{att_sum}={att_total}</code> vs "
        f"<code>{def_sum}={def_total}</code>"
    )


def wall_line(out: dict, by_slot: dict) -> str:
    rolls = out.get("wall_rolls") or []
    if not rolls:
        return ""
    rows = []
    for r in rolls:
        row = by_slot.get(r["slot"])
        if row is None:
            continue
        mark = "💨" if r["slot"] in (out.get("beaten") or []) else "🛡"
        rows.append(
            f"   {mark} <b>{row['name']}</b> <code>{r['die']}+{out['def_power']}</code>"
        )
    return "\n".join(rows)


def gk_line(out: dict) -> str:
    if out["gk_die"] is None:
        return ""
    eff = out.get("gk_total_eff")
    shown = eff if eff is not None else out["gk_total"]
    return (
        f"<code>{out['att_die']}+{out['att_power']}={out['att_total']}</code> vs "
        f"🧤<code>{out['gk_die']}+{out['gk_power']}={shown}</code>"
    )



# ------------------------------------------------------- Phase 7: commentary pools
# Base lines per outcome — describe() picks one at random so matches never read
# the same twice. Only the plain branches are swapped; skill/walk/gamble specials
# and every follow-up line (assist, nerve, wall, gk) stay deterministic.
COMMENTARY: dict[str, tuple[str, ...]] = {
    "goal": (
        f"⚽️ <b>GOAL — {{actor}}</b> beats {KEEPER_NAME}!",
        f"⚽️ <b>GOAL!</b> <b>{{actor}}</b> buries it — {KEEPER_NAME} never moved!",
        f"⚽️ <b>GOAL — {{actor}}</b> with ice in his veins! {KEEPER_NAME} beaten!",
        f"⚽️ <b>GOAL!</b> <b>{{actor}}</b> unleashes — and the net bulges past {KEEPER_NAME}!",
    ),
    "pass_ok": (
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — a sharp pass into the channel",
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — threaded through the line",
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — the delivery finds its mark",
    ),
    "dribble_ok": (
        "🌀 <b>{actor}</b> dribbles past <b>{defender}</b> — he's out of the play.",
        "🌀 <b>{defender}</b> buys the feint — <b>{actor}</b> is gone.",
        "🌀 <b>{actor}</b> twists away from <b>{defender}</b> — nothing but his back.",
    ),
    "tackled": (
        "🦵 <b>{defender}</b> takes the ball off <b>{actor}</b>.",
        "🦵 <b>{defender}</b> times it perfectly — <b>{actor}</b> loses it.",
        "🦵 clean challenge — <b>{defender}</b> rips it off <b>{actor}</b>.",
    ),
    "intercepted": (
        "🚫 <b>{defender}</b> reads <b>{actor}</b>'s delivery.",
        "🚫 <b>{defender}</b> cuts it out — <b>{actor}</b>'s ball never arrives.",
        "🚫 <b>{defender}</b> sees it coming and steps in front of <b>{actor}</b>.",
    ),
    "saved": (
        f"🧤 <b>{KEEPER_NAME}</b> denies <b>{{actor}}</b> —",
        f"🧤 <b>{KEEPER_NAME}</b> shuts the door on <b>{{actor}}</b> —",
        f"🧤 huge hands — <b>{KEEPER_NAME}</b> answers <b>{{actor}}</b> —",
    ),
    "blocked": (
        "🧱 <b>{defender}</b> blocks <b>{actor}</b>'s effort.",
        "🧱 <b>{defender}</b> throws himself in — <b>{actor}</b>'s path is closed.",
        "🧱 brave defending — <b>{defender}</b> shuts <b>{actor}</b> down.",
    ),
    "wall": (
        f"🧱 <b>{{actor}}</b>'s effort is swarmed — the wall holds.",
        f"🧱 the wall stands tall — <b>{{actor}}</b>'s shot crashes off it.",
        f"🧱 bodies everywhere — <b>{{actor}}</b> can't punch through.",
    ),
}


def commentary(key: str, **kw) -> str:
    """Pick one random base line from a COMMENTARY pool and render it."""
    return random.choice(COMMENTARY[key]).format(**kw)


def big_moment_lines(out: dict, goals: int) -> list[str]:
    """Extra hype lines for a goal — hat-trick, gamble payoff.

    Quiet goals return nothing: every added line must earn its place.
    """
    notes: list[str] = []
    if goals >= 3:
        notes.append("🎩 <b>HAT-TRICK!</b>")
    if out.get("gamble_beaten"):
        notes.append(f"🎲 <b>RISK PAID OFF</b> — {out['gamble_beaten']} beaten on the die.")
    return notes


def describe(out: dict, by_slot: dict | None = None) -> str:
    actor = out["actor"]["name"]
    outcome = out["outcome"]
    duel = duel_line(out)
    wall_txt = wall_line(out, by_slot or {})
    defender = out["defender"]["name"] if out["defender"] else "—"
    free = " <i>(unmarked — everyone's beaten)</i>" if out.get("unmarked") else ""

    if outcome == "pass_ok":
        if out.get("walked"):
            line = f"🎯 <b>{actor}</b> ➜ <b>{out['target']['name']}</b> — a casual ball into open space. <i>No duel needed.</i>"
        else:
            line = commentary("pass_ok", actor=actor, target=out["target"]["name"]) + f".{free} {duel}"
        if out.get("pass_advanced"):
            line += "\n     ➡️ the cut-back carries the play a zone forward"
        return line
    if outcome == "cross_ok":
        return (
            f"📢 <b>{actor}</b> swings the free kick into <b>{out['target']['name']}</b> — "
            f"delivery arrived.{free} {duel}"
        )
    if outcome == "intercepted":
        line = commentary("intercepted", actor=actor, defender=defender) + f" {duel}"
        if out.get("stopped_by_skill"):
            line = f"🚫 <b>{out['stopped_by_skill']['name']}</b> snuffs out <b>{actor}</b>'s play before it begins."
        if out.get("first_free"):
            line += "\n     🔁 <b>…but the loss doesn't count.</b> <i>One more try.</i>"
        return line
    if outcome == "dribble_ok":
        if out.get("stopped_by_skill"):
            return f"🌀 <b>{actor}</b> leaves <b>{defender}</b> grasping at air — gone."
        if out.get("gamble_beaten"):
            return (
                f"🎲 <b>{actor}</b> rolls the dice and ghosts past <b>{defender}</b> —"
                f" <b>{out['gamble_beaten']}</b> defenders beaten without a fight.{free}"
            )
        if out["defender"] is None:
            if out.get("walked"):
                return f"🚶 <b>{actor}</b> advances unopposed — the road ahead is clear.{free}"
            return f"🌀 <b>{actor}</b> drives forward — no one left to stop him.{free}"
        return commentary("dribble_ok", actor=actor, defender=defender) + f" {duel}"
    if outcome == "tackled":
        if out.get("stopped_by_skill"):
            return f"🦵 <b>{out['stopped_by_skill']['name']}</b> wins the ball off <b>{actor}</b> outright."
        return commentary("tackled", actor=actor, defender=defender) + f" {duel}"
    if outcome == "blocked":
        if out.get("gamble_backfire"):
            return f"💀 <b>{actor}</b>'s gamble collapses — <b>{defender}</b> was ready for it all along."
        if out.get("stopped_by_skill"):
            return f"🧱 <b>{out['stopped_by_skill']['name']}</b> throws himself in front of <b>{actor}</b>'s effort."
        line = commentary("blocked", actor=actor, defender=defender) + f" {duel}"
        if out["action"] == "shoot":
            line = commentary("wall", actor=actor) + f" {duel}"
            if wall_txt:
                line = commentary("wall", actor=actor)
                line += "\n" + wall_txt
        if out.get("first_free"):
            line += "\n     🔁 <b>…but the loss doesn't count.</b> <i>One more try.</i>"
        return line
    if outcome == "goal":
        line = commentary("goal", actor=actor)
        if out["action"] == "penalty":
            line += f"\n     🎯 <b>{out['att_spot']}</b> in — keeper dived {out['gk_spot']}"
            if out.get("nerve"):
                line += f"\n     ⚡️ nerve duel <code>{out['pen_sho']}</code> vs <code>{out['pen_gk']}</code>"
            return line
        if out["action"] == "shoot" and wall_txt:
            line += "\n     🧱 every defender beaten:"
            line += "\n" + wall_txt
        elif duel:
            line += f"\n     🛡 {duel}"
        elif out["action"] == "freekick":
            line += "\n     🎯 straight off the dead ball"
        else:
            line += "\n     🛡 no marker left — free shot"
        line += f"\n     🧤 {gk_line(out)}"
        if out.get("assister"):
            line += f"\n     🅰 Assist — <b>{out['assister']['name']}</b>"
        return line
    if outcome == "saved":
        catch = out.get("keeper_dist") == "catch"
        head = "holds it 🧤" if catch else "punches it away 💥"
        line = commentary("saved", actor=actor) + f" {head}"
        if out["action"] == "penalty":
            line += f"\n     🎯 shot {out['att_spot']} — keeper read it"
            line += f"\n     ⚡️ nerve duel <code>{out.get('pen_sho')}</code> vs <code>{out.get('pen_gk')}</code>"
            return line
        if out["action"] == "shoot" and wall_txt:
            line += "\n     🧱 the whole wall was brushed aside:"
            line += "\n" + wall_txt
        elif duel:
            line += f"\n     🛡 {duel}"
        line += f"\n     🧤 {gk_line(out)}"
        if not catch:
            line += f"\n     ➜ loose ball falls to <b>{out['receiver']['name']}</b>"
        return line
    if outcome == "foul":
        piece = "PENALTY 🥶" if out["set_piece"] == "penalty" else "FREE KICK 🎯"
        reason = out.get("reason")
        if reason == "drawn":
            return f"🎭 <b>{actor}</b> wins the referee's whistle — <b>{piece}</b>! {duel}"
        if wall_txt:
            base = f"⚖️ Deadlock — <b>{piece}</b> for <b>{actor}</b>. {duel}"
            base += "\n" + wall_txt
            return base
        return f"⚖️ Deadlock — <b>{piece}</b> for <b>{actor}</b>. {duel}"
    return duel
