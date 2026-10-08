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
    PENALTY_TARGETS,
    STAT_NAME,
    ZONE_BOX,
    ZONE_SHOOT,
    max_turns,
)
from .render import (
    COMMENTARY,
    big_moment_lines,
    commentary,
    describe,
    duel_line,
    gk_line,
    wall_line,
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
    state["stamp"] = {"turn": 1, "at": db.now()}
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


def _contest_actions(cfg: dict, action: str) -> bool:
    acts = cfg.get("action")
    if isinstance(acts, str):
        return action == acts
    return action in (acts or ())


def _start_contest(duel: dict, ab, cfg: dict, a_slot: int, d_slot: int, owner: str) -> None:
    secret = cfg.get("secret", "a")
    duel["contest"] = {
        "aid": ab.id, "src": ab.name, "owner": owner,
        "a_slot": a_slot, "d_slot": d_slot,
        "set_slot": a_slot if secret == "a" else d_slot,
        "call_slot": d_slot if secret == "a" else a_slot,
        "secret": secret,
        "a": cfg.get("a", []), "d": cfg.get("d", []),
        "matrix": cfg.get("matrix", {}),
    }


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
    used_before = set(state.get("used", []))
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
            state.setdefault("pending_goals", []).append(
                {"owner": actor["slot"], "src": ab.id,
                 "self_amt": ab.goal_self, "mate_amt": ab.goal_mate})

    if armed is not None and _gated(armed, ctx_att):
        if armed.auto == "win":
            abilities.spend_armed(state, actor["slot"])
            _stash_goal(armed)
            duel["auto"] = {"t": "win", "slot": actor["slot"], "aid": armed.id}
            duel["zone_extra"] = armed.zone_extra
            if armed.puppet and action == "pass" and duel.get("target") is not None:
                duel["puppet"] = {"rin": actor["slot"], "mate": duel["target"], "aid": armed.id}
            abilities.note(state, actor["name"], armed, icon=abilities.icon_for(armed))
        elif (armed.contest is not None and defender is not None
              and not duel.get("contest")
              and _contest_actions(armed.contest, action)):
            abilities.spend_armed(state, actor["slot"])
            _stash_goal(armed)
            _start_contest(duel, armed, armed.contest, actor["slot"], defender["slot"], "a")
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
                # A threaded shot faces at most N of the
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
                if armed.beat_keeper:
                    # Dance: the run starts here and ends past the keeper.
                    state["beat_gk"] = {"slot": actor["slot"], "src": armed.id}
                if armed.dribble_stack and val:
                    # Monster mode starts on this dribble; every one after it
                    # tops the stack up (+1 until the next goal).
                    state["monster"] = {"slot": actor["slot"], "amt": 0, "src": armed.id}
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

    # Bachira's Monster stack rides on every action of his until a goal wipes it.
    _mon = state.get("monster")
    if _mon and _mon.get("slot") == actor["slot"] and _mon.get("amt"):
        duel["att_power"] += _mon["amt"]
        duel["att_boosts"].append(("Monster Moment", _mon["amt"]))
        _mab = abilities.get(_mon.get("src", ""))
        if _mab:
            abilities.note(state, actor["name"], _mab,
                           f"monster stack +{_mon['amt']}", icon="👹")

    # Dance: he danced past the whole defence on his dribble — now the keeper.
    _bg = state.get("beat_gk")
    if _bg and _bg.get("slot") == actor["slot"] and action == "shoot":
        duel["beat_keeper"] = True
        state.pop("beat_gk", None)
        _bkg = abilities.get(_bg.get("src", ""))
        if _bkg:
            abilities.note(state, actor["name"], _bkg,
                           "the keeper is just another man to go around", icon="💃")

    # Knight Defense: the ball he won came with a bonus attached, and it rides
    # every action of his for as long as he keeps the ball.
    _hb = state.get("hold_buff")
    if _hb and _hb.get("slot") == actor["slot"] and match["holder"] == actor["slot"]:
        duel["att_power"] += _hb["amt"]
        duel["att_boosts"].append((_hb.get("name", "Knight Defense"), _hb["amt"]))
        _hab = abilities.get(_hb.get("src", ""))
        if _hab:
            abilities.note(state, actor["name"], _hab,
                           f"riding the ball +{_hb['amt']}", icon="🛡")

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
        if (d_armed.contest is not None and not duel.get("contest")
                and _contest_actions(d_armed.contest, action)):
            abilities.spend_armed(state, row["slot"])
            _start_contest(duel, d_armed, d_armed.contest, actor["slot"], row["slot"], "d")
            abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))
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
                if d_armed.hold_bonus and (ctx_def.get("mode") or "defense") == "defense":
                    # paid out if winning the ball puts it at his feet
                    state["pending_hold"] = {"slot": row["slot"], "amt": d_armed.hold_bonus,
                                             "name": d_armed.name, "src": d_armed.id}
        else:
            if d_armed.die_floor:
                abilities.spend_armed(state, row["slot"])
                duel[floor_key] = d_armed.die_floor
                abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))

    if defender is not None:
        _defender_arms(defender, "def_power", "def_boosts", "def_floor")
    for w in wall[1:]:
        if isinstance(duel.get("auto"), dict) and duel["auto"].get("t") == "stop":
            break
        _defender_arms(by_slot[w], "def_power", "def_boosts", "def_floor")
        if isinstance(duel.get("auto"), dict) and duel["auto"].get("t") == "stop":
            duel["defender"] = by_slot[w]["slot"]
            break

    if action == "penalty":
        keeper_captain = team_captain(roster, defender_team(actor))
        duel["spotter"] = keeper_captain["slot"] if keeper_captain else None
        duel["att_spot"] = None
        duel["gk_spot"] = None
        if keeper_captain is not None:
            k_ab = abilities.peek_armed(state, keeper_captain["slot"])
            if k_ab is not None and k_ab.auto == "stop" and _gated(
                k_ab, abilities.build_ctx(match, roster, keeper_captain, actor, action, zone, state)
            ):
                abilities.spend_armed(state, keeper_captain["slot"])
                duel["auto"] = {"t": "stop", "slot": keeper_captain["slot"], "aid": k_ab.id}
                abilities.note(state, keeper_captain["name"], k_ab,
                               "penalty erased — no guess needed", icon="🧤")

    state["duel"] = duel
    # charges burned building this duel go back to the player if he undoes it
    _burned = [i for i in state.get("used", []) if i not in used_before]
    if _burned:
        state["duel_spent"] = _burned
    else:
        state.pop("duel_spent", None)
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
    duel_actor = (state.get("duel") or {}).get("actor")
    state.pop("duel", None)
    state.pop("notes", None)
    # an abandoned duel must not leave its payout behind for the next action
    state.pop("pending_buff", None)
    state.pop("pending_beats", None)
    if state.get("pending_goals"):
        state["pending_goals"] = [
            pg for pg in state["pending_goals"] if pg.get("owner") != duel_actor
        ]
        if not state["pending_goals"]:
            state.pop("pending_goals", None)
    # the charges this duel burned come back — nothing fired
    for _aid in state.pop("duel_spent", []) or []:
        _ab = abilities.get(_aid)
        if _ab is not None:
            abilities.refund(state, _ab)
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
    _c = duel.get("contest")
    if _c and (duel.get("contest_secret") is None or duel.get("contest_open") is None):
        roles = []
        if duel.get("contest_secret") is None:
            roles.append(("contest_set", "contest_secret", _c["set_slot"]))
        if duel.get("contest_open") is None:
            roles.append(("contest_call", "contest_open", _c["call_slot"]))
        return roles
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
    if role == "contest_set":
        out["label"] = "Make your move — it stays hidden"
    if role == "contest_call":
        out["label"] = "What's his move?"
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


def contest_side(cfg: dict, role: str) -> str:
    secret = cfg.get("secret", "a")
    return secret if role == "contest_set" else ("d" if secret == "a" else "a")


def contest_opts(cfg: dict, role: str) -> list:
    return cfg.get(contest_side(cfg, role)) or []


def _contest_choice_ok(role: str, choice: str, duel: dict) -> bool:
    cfg = (duel or {}).get("contest") or {}
    return any(choice == k for k, _ in contest_opts(cfg, role))


def submit_contest_set(match_id: int, user_id: int, choice: str) -> dict:
    match = db.match(match_id)
    if not match or match["phase"] != "duel":
        return {"status": "closed"}
    duel = pending_of(match).get("duel")
    if not _contest_choice_ok("contest_set", choice, duel):
        return {"status": "invalid"}
    return _claim(match_id, user_id, choice, ("contest_set",))


def _apply_contest_effect(c, match_id: int, state: dict, duel: dict, cfg: dict, eff: dict) -> None:
    winner = eff.get("win")
    if winner == "att":
        duel["auto"] = {"t": "win", "slot": cfg.get("a_slot"),
                        "aid": cfg.get("aid"), "contest": True}
    elif winner == "def":
        duel["auto"] = {"t": "stop", "slot": cfg.get("d_slot"),
                        "aid": cfg.get("aid"), "contest": True}
    if eff.get("sure"):
        duel["sure_goal"] = True
    if eff.get("zone"):
        duel["zone_extra"] = duel.get("zone_extra", 0) + int(eff["zone"])
    if eff.get("att"):
        duel["att_power"] = duel.get("att_power", 0) + int(eff["att"])
        duel.setdefault("att_boosts", []).append((cfg.get("src", "contest"), int(eff["att"])))
    if eff.get("def"):
        duel["def_power"] = duel.get("def_power", 0) + int(eff["def"])
        duel.setdefault("def_boosts", []).append((cfg.get("src", "contest"), int(eff["def"])))
    if eff.get("buff") and duel.get("target") is not None:
        from_name = ""
        prow = c.execute(
            "SELECT name FROM match_players WHERE match_id=? AND slot=?",
            (match_id, cfg.get("a_slot")),
        ).fetchone()
        if prow:
            from_name = prow["name"]
        state.setdefault("buffs", []).append({
            "slot": duel["target"], "amt": int(eff["buff"]),
            "src": cfg.get("aid"), "from": from_name,
        })
        state.setdefault("notes", []).append(
            f"✨ <b>{cfg.get('src')}</b> — receiver +{int(eff['buff'])}"
        )


def submit_contest_call(match_id: int, user_id: int, choice: str) -> dict:
    match = db.match(match_id)
    if not match or match["phase"] != "duel":
        return {"status": "closed"}
    duel = pending_of(match).get("duel")
    if not _contest_choice_ok("contest_call", choice, duel):
        return {"status": "invalid"}
    out = _claim(match_id, user_id, choice, ("contest_call",))
    if out.get("status") != "ok":
        return out
    with db.tx() as c:
        row = c.execute("SELECT pending FROM matches WHERE id=? AND phase='duel'", (match_id,)).fetchone()
        if not row:
            return out
        state = json.loads(row["pending"] or "{}")
        duel = state.get("duel") or {}
        cfg = duel.get("contest") or {}
        set_side = contest_side(cfg, "contest_set")
        a_pick = duel.get("contest_secret") if set_side == "a" else duel.get("contest_open")
        d_pick = duel.get("contest_open") if set_side == "a" else duel.get("contest_secret")
        eff = (cfg.get("matrix") or {}).get(f"{a_pick}_{d_pick}") or {}
        _apply_contest_effect(c, match_id, state, duel, cfg, eff)
        state.setdefault("notes", []).append(
            f"🧠 <b>{cfg.get('src')}</b> — the read lands: "
            f"<code>{a_pick}</code> vs <code>{d_pick}</code>"
        )
        c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
    out["a_pick"] = a_pick
    out["d_pick"] = d_pick
    out["effect"] = eff
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


def arm_skill(match_id: int, user_id: int, ability_id: str,
              mode: str | None = None) -> dict:
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
        if mode in ("defense", "sword"):
            # the stance he picks when he arms it (Knight Defense / Knight Sword)
            state.setdefault("modes", {})[str(me["slot"])] = mode
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
        if not is_holder and not is_defensive(ab) and not ab.steal_on_arm:
            return {"status": "notturn", "name": ab.name}
        current[mine_key] = ability_id
        stole = False
        if ab.steal_on_arm and match["phase"] == "play" and not is_holder:
            holder_row = next((r for r in roster if r["slot"] == holder_slot), None)
            if holder_row is None or holder_row["team"] != me["team"]:
                # the read lands the instant he arms it — the ball is his now
                c.execute("UPDATE matches SET holder=? WHERE id=?", (me["slot"], match_id))
                state["beaten"] = []
                state["last_pass"] = None
                state["chain"] = 0
                stole = True
        c.execute("UPDATE matches SET pending=? WHERE id=?", (json.dumps(state), match_id))
        out = {"status": "armed", "name": ab.name, "kind": ab.kind}
        if stole:
            out["stole"] = True
            out["you"] = me["name"]
        return out


def is_defensive(ab) -> bool:
    return (ab.auto == "stop" or ab.punch_to_self or ab.dfd is not None
            or ab.first_free or ab.contest is not None or bool(ab.aura_gk))


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

    def _uctx(self_row, other_row):
        return abilities.build_ctx(match, roster, self_row, other_row, action, zone, state)
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
        if d_armed is None or d_armed.gamble:
            continue
        ctx_def = _uctx(row, actor)
        if not _gated(d_armed, ctx_def):
            continue
        if d_armed.auto == "stop":
            abilities.spend_armed(state, slot)
            duel["auto"] = {"t": "stop", "slot": slot, "aid": d_armed.id}
            duel["defender"] = slot
            defender = row
            abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))
            break
        if d_armed.dfd is None:
            continue
        try:
            val = d_armed.dfd(ctx_def) or 0
        except Exception:
            val = 0
        if val and (d_armed.name, val) not in _seen_boosts:
            abilities.spend_armed(state, slot)
            duel["def_power"] += val
            duel["def_boosts"].append((d_armed.name, val))
            abilities.note(state, row["name"], d_armed, icon=abilities.icon_for(d_armed))
            if d_armed.hold_bonus and (ctx_def.get("mode") or "defense") == "defense":
                state["pending_hold"] = {"slot": slot, "amt": d_armed.hold_bonus,
                                         "name": d_armed.name, "src": d_armed.id}

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
    if duel.get("gamble") and auto is None:
        die = duel.get("att_die") or 1
        gamble_min = duel.get("gamble_min", 0)
        if gamble_min and die < gamble_min:
            out["gamble_backfire"] = True
            if defender is not None:
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
        state.pop("monster", None)   # the stack dies with the goal, like any buff
        # Knight Defense: winning the ball brings the stance bonus with it, and
        # losing it takes the bonus away.
        state.pop("beat_gk", None)   # the dance ends if the ball changes hands
        _ph = state.pop("pending_hold", None)
        if _ph and _ph.get("slot") == slot:
            state["hold_buff"] = _ph
        elif (state.get("hold_buff") or {}).get("slot") != slot:
            state.pop("hold_buff", None)
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
        state.pop("loose_claim_slot", None)   # that read expires at the next goal
        # Taha's duration rules: every goal reward expires at the NEXT goal;
        # a mid-match streak expires when its own holder scores.
        state["streaks"] = [
            s for s in state.get("streaks", [])
            if s.get("kind") != "reward" and s.get("slot") != actor["slot"]
        ]
        # Passive goal payout: owed to the owner once his team scores.
        # Granted AFTER the sweep so it survives this goal and the next one
        # wipes it. The pendings are dropped either way.
        for pg in state.pop("pending_goals", []):
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
        nonlocal new_holder, actor
        out["outcome"] = "saved"
        out["keeper_dist"] = "catch" if catch else "punch"
        receiver = None
        if not catch:
            self_ab = abilities.peek_armed(state, actor["slot"])
            if self_ab is not None and not _gated(
                self_ab, _uctx(actor, defender)
            ):
                self_ab = None
            if (self_ab is not None and self_ab.save_self) or duel.get("save_self"):
                if self_ab is not None and self_ab.save_self:
                    abilities.spend_armed(state, actor["slot"])
                receiver = actor
            else:
                for r in roster:
                    if r["team"] == defender_team(actor):
                        d_ab = abilities.peek_armed(state, r["slot"])
                        if d_ab is not None and not _gated(
                            d_ab, _uctx(r, actor)
                        ):
                            d_ab = None
                        if d_ab is not None and d_ab.punch_to_self:
                            abilities.spend_armed(state, r["slot"])
                            receiver = r
                            abilities.note(state, r["name"], d_ab, "loose ball claimed")
                            break
        if receiver is None and catch:
            mates = [r for r in roster if r["team"] == defender_team(actor)]
            receiver = random.choice(mates) if mates else actor
        if receiver is None:
            # A ball nobody held: a passive tuned to loose balls beats the coin
            # flip — Barou comes and takes it, Sae comes and finishes it.
            claimed = None
            lab = None
            for r in roster:
                if r["team"] != actor["team"]:
                    continue
                _lb = abilities.peek_armed(state, r["slot"])
                if _lb is not None and _lb.on_ball_loose:
                    abilities.spend_armed(state, r["slot"])
                    claimed = r
                    lab = _lb
                    abilities.note(state, r["name"], _lb, "reads the loose ball",
                                   icon=abilities.icon_for(_lb))
                    break
            if claimed is not None:
                receiver = claimed
                state["loose_claim_slot"] = claimed["slot"]
                if lab.finish_loose:
                    out["receiver"] = claimed
                    out["loose_finish"] = True
                    _shooter = actor
                    actor = claimed          # credit the finish, not the shooter
                    score_goal()
                    actor = _shooter
                    return
            else:
                receiver = loose_ball_to(roster, actor, beaten)
        out["receiver"] = receiver
        new_holder = turnover(receiver["slot"])

    if auto is not None and auto["t"] == "stop":
        stopper = by_slot[auto["slot"]]
        if action == "penalty":
            out["outcome"] = "saved"
            out["erased"] = True
        else:
            out["outcome"] = {"pass": "intercepted", "cross": "intercepted", "dribble": "tackled"}.get(action, "blocked")
        out["stopped_by_skill"] = stopper
        db.bump_slot(match_id, stopper["slot"], stops=1)
        new_holder = turnover(stopper["slot"])
    elif deadlock:
        award_piece("deadlock")
    elif not cleared:
        lost_ab = abilities.peek_armed(state, actor["slot"])
        if lost_ab is not None and not _gated(
            lost_ab, _uctx(actor, defender)
        ):
            lost_ab = None
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
            if isinstance(auto, dict) and auto.get("t") == "stop" and auto.get("slot") is not None:
                stopper = by_slot.get(auto["slot"]) or stopper
            elif action == "shoot":
                for slot in duel.get("wall") or []:
                    die = duel.get(f"die_{slot}")
                    if die is None:
                        break
                    snapshot = {**duel, "defender": slot, "def_die": die}
                    if past_defender(snapshot, slot) is not True:
                        stopper = by_slot[slot]
                        break
            if stopper is None:
                stopper = next((r for r in roster if r["team"] != actor["team"]), None)
            if stopper is not None:
                db.bump_slot(match_id, stopper["slot"], stops=1)
                new_holder = turnover(stopper["slot"])
    elif action == "penalty":
        # No dice: the corner call decides it. A read corner is a guaranteed stop,
        # a missed corner is a guaranteed goal — abilities only push the keeper off
        # the shooter's corner, they never break the read.
        gk_spot = out["gk_spot"]
        spot_row = by_slot.get(duel.get("spotter"))
        erased = isinstance(auto, dict) and auto.get("t") == "stop"
        if not erased and spot_row is not None:
            k_ab = abilities.peek_armed(state, spot_row["slot"])
            if k_ab is not None and k_ab.auto == "stop" and _gated(
                k_ab, _uctx(spot_row, actor)
            ):
                abilities.spend_armed(state, spot_row["slot"])
                abilities.note(state, spot_row["name"], k_ab, "penalty erased — no guess needed", icon="🧤")
                erased = True
        if erased:
            keeper_restart(catch=True)
            out["erased"] = True
        else:
            pen_ab = abilities.peek_armed(state, actor["slot"])
            if pen_ab is not None and not _gated(
                pen_ab, _uctx(actor, defender)
            ):
                pen_ab = None
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
        if shot_ab is not None and not _gated(
            shot_ab, _uctx(actor, defender)
        ):
            shot_ab = None
        down = duel.get("gk_down", 0)
        margin = duel.get("save_margin", 0)
        tie = bool(duel.get("tie_win"))
        if shot_ab is not None and (shot_ab.gk_down or shot_ab.save_margin or shot_ab.tie_win):
            abilities.spend_armed(state, actor["slot"])
            down = down or shot_ab.gk_down
            margin = margin or shot_ab.save_margin
            tie = tie or bool(shot_ab.tie_win)
            abilities.note(state, actor["name"], shot_ab, "ultimate strike" if down >= 3 else "clinical finish")
        # keeper aura passives: armed by the defending side (mid-duel too) and
        # burned on the shot they actually lift the keeper against
        aura = 0
        for r in roster:
            if r["team"] != defender_team(actor) or r["user_id"] is None:
                continue
            au = abilities.peek_armed(state, r["slot"])
            if au is None or not au.aura_gk:
                continue
            if not _gated(au, _uctx(r, actor)):
                continue
            abilities.spend_armed(state, r["slot"])
            aura += au.aura_gk
            abilities.note(state, r["name"], au, f"keeper +{au.aura_gk}", icon="🧤")
        eff_gk_total = total(duel, "gk") - down + aura
        if down or aura:
            out["gk_total_eff"] = eff_gk_total
        if aura:
            out["gk_aura"] = aura
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
        elif duel.get("beat_keeper"):
            # Dance ends — he went around the keeper rather than over him.
            won = True
            out["beat_keeper"] = True
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
            if buff_ab is not None and not _gated(
                buff_ab, _uctx(actor, defender)
            ):
                buff_ab = None
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
            if buff_ab is not None and not _gated(
                buff_ab, _uctx(actor, defender)
            ):
                buff_ab = None
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

    # --- Threaded move (through 1..N) — leftovers of a threaded shot are already
    # tagged at open_duel; a carry/pass rolls its band NOW (attack die, capped by
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
    # dealt on the goal and survives it (any goal clears it).
    state.pop("pending_hold", None)   # never won the ball → never paid
    pb = state.pop("pending_beats", None)
    if pb:
        _pb_ab = abilities.get(pb.get("src", ""))
        # everyone THIS move put on the floor — wall roll, marker, or the
        # through band. Already-beaten players keep their old tag.
        _targets = [s for s in beaten
                    if s not in beaten_before and s != actor["slot"]]
        for _slot in _targets:
            grant_streak(state, _slot, pb["amt"], pb.get("src", ""), kind="reward")
        if _pb_ab and _targets:
            abilities.note(state, actor["name"], _pb_ab,
                           f"{len(_targets)} beaten → {pb['amt']} until the next goal",
                           icon="👑")

    # Monster Moment: every dribble he lands adds one more to the stack.
    _mon = state.get("monster")
    if (_mon and _mon.get("slot") == actor["slot"] and action == "dribble"
            and out.get("outcome") == "dribble_ok"):
        _mon["amt"] = _mon.get("amt", 0) + 1
        _mab = abilities.get(_mon.get("src", ""))
        if _mab:
            abilities.note(state, actor["name"], _mab,
                           f"dribble → stack now +{_mon['amt']}", icon="👹")

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



