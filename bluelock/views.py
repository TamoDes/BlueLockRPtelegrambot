import json

from telebot import types

from . import abilities, db, economy, engine
from .characters import ROSTER, effective_stats, epithet_of, icon_of, name_of, overall, role_of
from .config import (
    BOUND_ENABLED,
    BOOST_LEVELS,
    BOUND_TIER_COST,
    BOUND_TIER_LEVEL,
    GOAL_TARGET,
    KEEPER_CATCH_ROLL,
    KEEPER_NAME,
    KEEPER_POWER,
    LOG_KEEP,
    MAX_BOUND_TIER,
    MAX_BOOST,
    MAX_SKILL_SLOTS,
    MAX_STAT,
    MODES,
    REROLL_COST,
    SKILL_SLOT_COST,
    STATS,
    TITLE_COST,
    STAT_ABBR,
    ZONE_NAME,
    boosts_allowed,
    level_for,
    rank_for,
    train_cost,
    xp_for_level,
)
from .fmt import (
    HEAVY,
    RULE,
    kv_line,
    bar,
    clip,
    esc,
    header,
    hint,
    mono,
    place,
    quote,
    yen,
    yen_short,
)

TEAM_ICON = {1: "🔵", 2: "🔴"}
KIND_ICON = {"passive": abilities.PASSIVE_ICON, "skill": abilities.SKILL_ICON}
TIER_TAG = {1: "", 2: " · II", 3: " · III", 4: " · ULT"}


def stat_block(eff: dict[str, int]) -> str:
    rows = [f"{STAT_ABBR[s]} {eff[s]:>2} {bar(eff[s], MAX_STAT)}" for s in STATS]
    return mono(rows) + "\n"



def goal_card_text(out: dict, by_slot: dict, celebration: str | None = None) -> str:
    """Phase 7 goal card: scorer + duel score + skills + personal celebration."""
    from .fmt import esc

    actor = out.get("actor") or {}
    name = esc(actor.get("name") or "?")
    lines = [f"⚽️ <b>GOAL</b> — <b>{name}</b>"]
    row = by_slot.get(actor.get("slot"))
    if row is not None and row.get("char_key"):
        lines.append(f"🎴 {esc(name_of(row['char_key']))}")
    if out.get("action") == "penalty":
        lines.append(
            f"🎯 penalty {out.get('att_spot')} in — keeper dived {out.get('gk_spot')}"
        )
    elif out.get("att_total") is not None and out.get("defender") is not None and out.get("def_total") is not None:
        lines.append(f"⚔️ duel <code>{out['att_total']}</code> vs <code>{out['def_total']}</code>")
    boosts = out.get("att_boosts") or []
    if boosts:
        lines.append("⚡ " + " · ".join(f"{esc(n)} +{v}" for n, v in boosts))
    if out.get("assister"):
        lines.append(f"🅰 Assist — <b>{esc(out['assister'].get('name') or '?')}</b>")
    if celebration:
        lines.append(f"\n🎉 {esc(celebration)}")
    return "\n".join(lines)

def clock(turn: int, total_turns: int) -> str:
    return f"{min(90, round(90 * turn / max(1, total_turns)))}′"


def rules_text() -> str:
    return (
        "📖 <b>How it works</b>\n"
        "<i>Blue Lock — dice football, phone-sized.</i>\n"
        + HEAVY
        + "\n🌀 <b>Build-up</b>\nPass ➜ Dribble ➜ Shoot. Every action duels"
        " the best free defender:\n<code>your stat + 🎲 vs MET + 🎲</code>\n"
        "Win and he's beaten for this attack.\n"
        "➡️ <b>Advance</b> — every opponent beaten ➜ dribble a zone forward, no dice.\n"
        "⚖️ Exact tie = deadlock ➜ set piece for the attacker."
        + "\n🎯 <b>Deadlock</b>\n<b>Box → PENALTY</b> 🥶 · anywhere else → <b>FREE KICK</b> 🎯."
        + "\n🥶 <b>Free Kick</b>\n<b>Direct</b> — FRK+🎲 vs the keeper alone, no wall."
        "\n<b>Cross</b> — FRK+🎲 vs the best defender; lands in the Final Third with an assist waiting."
        + "\n🥶 <b>Penalty</b>\nNo dice. You pick a corner, their captain calls the dive."
        "\nWrong corner → goal. Read corner → <b>always kept out</b>."
        + "\n\n🛡 <b>Passives</b> — <b>tap to arm</b> (they never fire on their own), <b>one charge</b> per match, always free."
        "\n⚡ <b>Skills</b> = one per match (2 with an extra skill slot); arm with the ⚡ button. 🎲 <b>Gamble</b> = the die decides."
        + quote("Every character fields six abilities — two innate, four earned through levels and yen. Full details in /abilities.")
        + "\n🏃 <b>Rotation</b> — every goal turns the positions, volleyball style: the back line steps forward."
        + "\n🏁 Ranked races to <b>3</b>. Friendly matches run the clock."
    )


def keeper_card() -> str:
    return (
        f"🧤 <b>{esc(KEEPER_NAME)}</b>\n"
        + mono([f"PWR {KEEPER_POWER}  {bar(KEEPER_POWER, MAX_STAT)}"]) + "\n"
        + f"<i>Open play:</i> your total vs his <code>d6 + {KEEPER_POWER}</code>.\n"
        f"<i>Direct FK:</i> no wall — keeper faces you alone.\n"
        f"<i>Catch {KEEPER_CATCH_ROLL}+</i> — otherwise punched clear.\n"
        + "<i>Penalty: corners only, no dice. Corner right → always stopped; "
        "corner wrong → always a goal.</i>"
    )


def zone_track(zone: int) -> str:
    return " ".join("◆" if i == zone else "◇" for i in range(len(ZONE_NAME)))


def lobby_text(match, roster) -> str:
    size = match["size"]
    mode = MODES.get(match["mode"], match["mode"])
    rule = (
        f"🥇 First to <b>{GOAL_TARGET}</b>"
        if engine.race_to_goals(match)
        else f"⏱ <b>{engine.turn_limit(match)}</b> actions"
    )

    def side(team: int) -> str:
        names = [r["name"] for r in roster if r["team"] == team]
        filled = "".join("●" if i < len(names) else "○" for i in range(size))
        rows = [f"  • {esc(n)}" for n in names] or ["  <i>— empty —</i>"]
        return f"{TEAM_ICON[team]} <b>{'Blue' if team == 1 else 'Red'}</b> <code>{filled}</code>\n" + "\n".join(rows)

    return (
        f"⚔️ <b>LOBBY #{match['id']}</b>\n"
        f"{mode} · <b>{size} v {size}</b> · {rule}\n"
        + RULE + "\n"
        + side(1) + "\n"
        + RULE + "\n"
        + side(2) + "\n"
        + RULE + "\n"
        "<i>Tap your team to join. Exact-tie duels in the box hand you a penalty —"
        " outside, a free kick. Ranked is first to 3.</i>"
    )


def lobby_keyboard(match, roster) -> types.InlineKeyboardMarkup:
    mid = match["id"]
    size = match["size"]
    c1 = sum(1 for r in roster if r["team"] == 1)
    c2 = sum(1 for r in roster if r["team"] == 2)
    ready = match["status"] == "open" and c1 == size and c2 == size
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"🔵 Blue {c1}/{size}", callback_data=f"join|{mid}|1"),
        types.InlineKeyboardButton(f"🔴 Red {c2}/{size}", callback_data=f"join|{mid}|2"),
    )
    if ready:
        kb.add(types.InlineKeyboardButton("🟢 Kickoff", callback_data=f"kick|{mid}"))
    kb.add(
        types.InlineKeyboardButton("🚪 Leave", callback_data=f"quit|{mid}"),
        types.InlineKeyboardButton("✖ Close", callback_data=f"cancel|{mid}"),
    )
    return kb


def remaining_charges(row, state) -> int:
    if not abilities.enabled():
        return 0
    used = set(state.get("used", []))
    charges = state.get("charges", {})
    n = 0
    for aid in abilities.owned_ids(row["user_id"], row["char_key"]):
        ab = abilities.get(aid)
        if not ab or aid in used:
            continue
        left = charges.get(aid)
        if left is None:
            left = abilities.PASSIVE_CHARGES if ab.kind == "passive" else 1
        n += max(0, left)
    return n


def scoreboard(match, roster) -> str:
    by_slot = {r["slot"]: r for r in roster}
    holder = by_slot.get(match["holder"])
    state = engine.pending_of(match)
    zone = state.get("zone", 0)
    beaten = set(state.get("beaten", []))
    buffs = {b["slot"]: b for b in state.get("buffs", [])}
    piece = state.get("set_piece")

    if match["status"] == "done":
        status = "🏁 Full time"
    elif engine.race_to_goals(match):
        status = f"🥇 Race to {GOAL_TARGET}"
    else:
        limit = engine.turn_limit(match)
        status = f"⏱ {clock(min(match['turn'], limit), limit)}"

    lines = {int(k): v for k, v in (state.get("lines", {}) or {}).items()}
    def block(team: int) -> str:
        rows = []
        for r in (x for x in roster if x["team"] == team):
            mark = "▸" if holder is not None and r["slot"] == holder["slot"] else "·"
            meta = []
            if r["goals"]:
                meta.append(f"⚽{r['goals']}")
            if r["assists"]:
                meta.append(f"🅰{r['assists']}")
            if r["slot"] in beaten:
                meta.append("💨")
            if r["slot"] in buffs:
                meta.append("✨")
            charges = remaining_charges(r, state)
            if charges:
                meta.append(f"⚡{charges}")
            tags = " ".join(meta)
            name = esc(r["name"])
            lane = engine.LANE_NAME[lines[r["slot"]]] if lines and r["slot"] in lines else ""
            extra = f" {tags}" if tags else ""
            rows.append(" ".join(x for x in (mark, lane, name + extra) if x))
        return "\n".join(rows) if rows else "  <i>—</i>"

    head = (
        f"⚽ <b>LIVE #{match['id']}</b>\n"
        f"{MODES.get(match['mode'], match['mode'])} {match['size']}v{match['size']} · {status}\n"
        + HEAVY + "\n"
        f"{TEAM_ICON[1]} <b>{match['score1']} — {match['score2']}</b> {TEAM_ICON[2]}\n"
        + RULE + "\n"
        f"{TEAM_ICON[1]} <b>Blue</b>\n{block(1)}\n"
        + RULE + "\n"
        f"{TEAM_ICON[2]} <b>Red</b>\n{block(2)}\n"
        + RULE + "\n"
    )

    pitch = f"📍 {ZONE_NAME[zone]} <code>{zone_track(zone)}</code>"
    if piece and match["status"] == "live":
        label = engine.ACTION_NAME[piece].upper()
        ask = " — Direct or Cross?" if piece == "freekick" else ""
        pitch += f"\n⚖️ <b>{label}</b> to take{ask}"
    if lines and match["status"] == "live":
        lane_rows = []
        for l in range(3):
            blue = sorted(s for s in lines if lines[s] == l and s in by_slot and by_slot[s]["team"] == 1)
            red = sorted(s for s in lines if lines[s] == l and s in by_slot and by_slot[s]["team"] == 2)
            if not blue and not red:
                continue
            blue_s = " ".join(f"{esc(by_slot[s]['name'])}" for s in blue) or "—"
            red_s = " ".join(f"{esc(by_slot[s]['name'])}" for s in red) or "—"
            lane_rows.append(f"{engine.LANE_NAME[l]:<8} 🔵 {blue_s:<14} 🔴 {red_s}")
        if lane_rows:
            pitch += "\n🗺️ <code>" + "\n    ".join(lane_rows) + "</code>"
    if beaten and match["status"] == "live":
        names = [by_slot[s]["name"] for s in beaten if s in by_slot]
        if names:
            pitch += f"\n💨 Beaten this attack: {', '.join(esc(n) for n in names)}"
    if holder is not None:
        armed_id = state.get("armed", {}).get(str(holder["slot"]))
        armed_ab = abilities.get(armed_id) if armed_id else None
        if armed_ab:
            pitch += f"\n{abilities.icon_for(armed_ab)} <b>Armed:</b> {esc(armed_ab.name)} — fires with his next play"
    body = head + pitch

    body += "\n"
    if match["phase"] == "duel":
        body += duel_board(match, roster)

    feed = db.recent_events(match["id"], LOG_KEEP)
    lines = [f"• {clip(line.splitlines()[0], 60)}" for line in feed]
    body += (
        RULE
        + "\n📻 <b>Feed</b>\n"
        + ("\n".join(lines) if lines else "• <i>Kick-off imminent…</i>")
    )
    return body


def duel_board(match, roster) -> str:
    state = engine.pending_of(match)
    pending = engine.awaiting(match)
    if not pending:
        return ""
    duel = pending["duel"]
    by_slot = {r["slot"]: r for r in roster}
    lines = [RULE]

    auto = duel.get("auto")
    action = duel["action"]

    if isinstance(auto, dict):
        ab = abilities.get(auto.get("aid", ""))
        title = esc(ab.name) if ab else "Signature move"
        lines.append(f"🎲 <b>{engine.ACTION_NAME[action]}</b> — ⚡ <b>{title}</b>")
        if action in engine.KEEPER_ACTIONS:
            lines.append("<i>Marker beaten without dice — only the keeper stands in the way.</i>")
        else:
            lines.append("<i>No dice needed. The play writes itself.</i>")
    elif action == "penalty":
        lines.append("🥶 <b>PENALTY</b> — corners, no dice")
        shot = "✅ locked" if duel["att_spot"] else "… thinking"
        dive = "✅ called" if duel["gk_spot"] else "… waiting"
        lines.append(f"🎯 Shooter {shot}")
        lines.append(f"🧤 Dive call {dive}")
    else:
        atk = f"{duel['att_power']}+🎲?" if duel["att_die"] is None else f"{duel['att_power']}+🎲{duel['att_die']}"
        lines.append(f"🎲 <b>{engine.ACTION_NAME[action]}</b>")
        lines.append(f"⚔️ ATK <code>{atk}</code>")
        wall = duel.get("wall") or []
        if action == "shoot" and wall:
            lines.append(f"🧱 <i>the whole wall steps up ({len(wall)} defenders):</i>")
            for slot in wall:
                name = esc(by_slot[slot]["name"]) if slot in by_slot else "?"
                die = duel.get(f"die_{slot}")
                ddie = "🎲?" if die is None else f"🎲{die}"
                lines.append(f"   🛡 {name} <code>{duel['def_power']}+{ddie}</code>")
        elif duel["defender"] is not None:
            d_name = esc(by_slot[duel["defender"]]["name"])
            ddie = "?" if duel["def_die"] is None else str(duel["def_die"])
            lines.append(f"🛡 {d_name} <code>{duel['def_power']}+🎲{ddie}</code>")
        elif action == "freekick":
            lines.append(f"🧤 Keeper alone <code>{duel['gk_power']}+🎲?</code>")
        else:
            lines.append("<i>no marker left — free run</i>")
        if action in engine.KEEPER_ACTIONS:
            gdie = "?" if duel["gk_die"] is None else str(duel["gk_die"])
            lines.append(f"🧤 Keeper <code>{duel['gk_power']}+🎲{gdie}</code>")

    for b in state.get("buffs", []):
        row = by_slot.get(b["slot"])
        if row:
            lines.append(f"✨ {esc(row['name'])} +{b['amt']} <i>(from {esc(b['from'])})</i>")

    role = pending["role"]
    who = esc(pending["name"])
    if role == "spot":
        prompt = f"🎯 <b>{who}</b> — pick your corner."
    elif role == "spot_gk":
        prompt = f"🧤 Defending captain <b>{who}</b> — where's he shooting?"
    elif role == "gk":
        prompt = "🧤 The keeper dives — bot rolls."
    elif isinstance(auto, dict):
        prompt = "⚡ Resolving…"
    else:
        prompt = f"→ Waiting on <b>{who}</b> — send 🎲"
    lines.append(prompt)
    return "\n".join(lines) + "\n"


ACTION_BUTTON = {
    "pass": "🅿️ Pass",
    "dribble": "🌀 Dribble",
    "shoot": "⚽ Shoot",
    "freekick": "🎯 Direct FK",
    "cross": "📢 Cross",
    "penalty": "🥶 Penalty",
    "advance": "➡️ Advance",
}

def ready_skills(row, state) -> list:
    """Unspent skills AND passives, ready to be armed from the action bar."""
    if not abilities.enabled() or row is None or row["user_id"] is None:
        return []
    out = []
    used = set(state.get("used", []))
    charges = state.get("charges", {})
    for aid in abilities.owned_ids(row["user_id"], row["char_key"]):
        ab = abilities.get(aid)
        if not ab or ab.id in used:
            continue
        left = charges.get(aid)
        if left is None:
            left = abilities.PASSIVE_CHARGES if ab.kind == "passive" else 1
        if left > 0:
            out.append(ab)
    return out


def _control_buttons(kb, mid) -> types.InlineKeyboardMarkup:
    kb.add(
        types.InlineKeyboardButton("🏳️ Surrender", callback_data=f"surrender|{mid}"),
        types.InlineKeyboardButton("📖 Rules", callback_data="rulesbtn"),
    )
    return kb


def action_keyboard(match, roster) -> types.InlineKeyboardMarkup:
    mid = match["id"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    if match["status"] != "live":
        return kb
    state = engine.pending_of(match)

    if match["phase"] == "duel":
        kb.add(types.InlineKeyboardButton("✋ Undo action", callback_data=f"undo|{mid}"))
        return kb

    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    has_mates = holder is not None and any(
        r["team"] == holder["team"] and r["slot"] != holder["slot"] for r in roster
    )
    actions = [a for a in engine.legal_actions(match) if a != "pass" or has_mates]
    actions = [a for a in actions if a != "cross" or has_mates]
    open_play = not state.get("set_piece") and match["phase"] != "duel"
    unmarked = open_play and not engine.marker(roster, holder["team"], state.get("beaten", [])) if holder else False
    if unmarked and "dribble" in actions and state.get("zone", 0) < engine.ZONE_BOX:
        actions = [a for a in actions if a != "dribble"]
        actions.append("advance")
    if actions and all(a in engine.SET_PIECES or a == "cross" for a in actions):
        kb.add(*[
            types.InlineKeyboardButton(ACTION_BUTTON[a], callback_data=f"act|{mid}|{a}|0")
            for a in actions
        ])
    else:
        kb.add(*[
            types.InlineKeyboardButton(
                ACTION_BUTTON[a],
                callback_data=(
                    f"menu|{mid}|pass" if a == "pass"
                    else f"advance|{mid}|{match['turn']}" if a == "advance"
                    else f"act|{mid}|{a}|0"
                ),
            )
            for a in actions
        ])

    for row in roster:
        if row["user_id"] is None:
            continue
        armed_id = state.get("armed", {}).get(str(row["slot"]))
        for sk in ready_skills(row, state):
            if not skill_usable_here(match, roster, row, sk, state):
                continue
            icon = abilities.icon_for(sk)
            if sk.id == armed_id:
                label = f"{icon} {sk.name} ✅ armed — tap to cancel"
            elif sk.kind == "passive":
                left = state.get("charges", {}).get(sk.id, abilities.PASSIVE_CHARGES)
                label = f"{icon} {sk.name} ×{max(1, left)}"
            else:
                label = f"{icon} {sk.name}"
            kb.add(types.InlineKeyboardButton(label, callback_data=f"skill|{mid}|{sk.id}"))

    return _control_buttons(kb, mid)


def skill_usable_here(match, roster, row, ab, state) -> bool:
    holder = match["holder"]
    is_holder = holder == row["slot"]
    defensive = engine.is_defensive(ab)
    if not is_holder and not defensive:
        return False
    if ab.when is None:
        return True
    zone = state.get("zone", 0)
    piece = state.get("set_piece")
    for action in engine.legal_actions(match):
        if piece and action != piece and action != "cross":
            continue
        try:
            ctx = abilities.build_ctx(match, roster, row, None, action, zone, state)
            if ab.when(ctx):
                return True
        except Exception:
            continue
    return False


def _receiver_keyboard(mid, action, holder, roster) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    mates = [r for r in roster if r["team"] == holder["team"] and r["slot"] != holder["slot"]]
    for r in mates:
        kb.add(types.InlineKeyboardButton(f"➜ {r['name']}", callback_data=f"act|{mid}|{action}|{r['slot']}"))
    kb.add(types.InlineKeyboardButton("↩︎ Back", callback_data=f"menu|{mid}|back"))
    return kb


def pass_keyboard(match, roster) -> types.InlineKeyboardMarkup:
    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    if holder is None:
        return types.InlineKeyboardMarkup()
    return _receiver_keyboard(match["id"], "pass", holder, roster)


def cross_keyboard(match, roster) -> types.InlineKeyboardMarkup:
    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    if holder is None:
        return types.InlineKeyboardMarkup()
    return _receiver_keyboard(match["id"], "cross", holder, roster)


def skill_hint(match_id: int, user_id: int, ab) -> str | None:
    match = db.match(match_id)
    if not match:
        return None
    roster = db.roster(match_id)
    me = next((r for r in roster if r["user_id"] == user_id), None)
    if me is None:
        return None
    tag = "🛡 passive" if ab.kind == "passive" else "⚡ skill"
    if ab.gamble:
        return f"🎲 <b>{esc(ab.name)}</b> ({tag}) — armed. The die decides the payoff."
    if ab.auto == "stop":
        return f"🛡 <b>{esc(ab.name)}</b> ({tag}) — armed: your next defensive duel auto-wins."
    if ab.punch_to_self:
        return f"🧤 <b>{esc(ab.name)}</b> ({tag}) — armed: you claim the keeper's punched ball."
    if ab.save_self:
        return f"🧤 <b>{esc(ab.name)}</b> ({tag}) — armed: you get the rebound if your shot is punched."
    if ab.pass_buff:
        return f"✨ <b>{esc(ab.name)}</b> ({tag}) — armed: next completed pass gives the receiver +{ab.pass_buff}."
    if ab.pass_advance:
        return f"➡️ <b>{esc(ab.name)}</b> ({tag}) — armed: receiver breaks {ab.pass_advance} zone(s), can't be intercepted."
    if ab.pen_edge:
        return f"🥶 <b>{esc(ab.name)}</b> ({tag}) — armed: pushes the keeper off your penalty corner."
    if ab.tackle_keep:
        return f"🌀 <b>{esc(ab.name)}</b> ({tag}) — armed: tackled → you keep the ball and advance."
    if ab.gk_down:
        return f"⚽ <b>{esc(ab.name)}</b> ({tag}) — armed: keeper −{ab.gk_down} on your shot."
    if ab.auto == "win":
        return f"⚡ <b>{esc(ab.name)}</b> ({tag}) — armed: beats your marker with no roll."
    if ab.dfd is not None:
        return f"🛡 <b>{esc(ab.name)}</b> ({tag}) — armed: extra power on your next marking duel."
    if ab.first_free:
        return f"🔁 <b>{esc(ab.name)}</b> ({tag}) — armed: your first lost duel doesn't count."
    if ab.att is not None:
        return f"⚡ <b>{esc(ab.name)}</b> ({tag}) — armed: fires on your next play in the right spot."
    return None


def kit_entries(row) -> list[str]:
    if not abilities.enabled():
        return []
    own = db.owned_by(row["user_id"])
    if not own:
        return []
    out = []
    for aid in abilities.owned_ids(row["user_id"], own["char_key"]):
        ab = abilities.get(aid)
        if ab:
            out.append(f"{KIND_ICON[ab.kind]} {ab.name}")
    return out


def kit_page(user_id: int, char_key: str) -> tuple[str, types.InlineKeyboardMarkup]:
    kb = types.InlineKeyboardMarkup(row_width=1)
    owned = set(abilities.owned_ids(user_id, char_key))
    head = (
        f"⚡ <b>EQUIPMENT</b>\n"
        f"{icon_of(char_key)}<b>{esc(name_of(char_key))}</b> · {overall(effective_stats(char_key, {}))} OVR\n"
        f"<i>{esc(role_of(char_key))}</i>\n{RULE}\n"
        "<i>🛡 passives arm themselves ×1 (free) · ⚡ skills = once per match · 🎲 gamble = the die decides</i>\n"
    )
    blocks = []
    for ab in abilities.kit_for_char(char_key):
        cost, need_lv = abilities.price_and_level(ab)
        icon = abilities.icon_for(ab)
        cat = abilities.category_of(ab)
        cat_tag = f" · {abilities.CATEGORY_ICON.get(cat, '·')} {cat}" if cat != "core" else ""
        kind_tag = " · passive ×1" if ab.kind == "passive" else ""
        if ab.bound:
            kind_tag += " · 🔗 bound"
        tag = TIER_TAG.get(ab.tier, "")
        title = f"{icon} <b>{ab.name}</b>{f'<i>{tag}{kind_tag}{cat_tag}</i>' if (tag or kind_tag or cat_tag) else ''}"
        if ab.id in owned:
            blocks.append(
                f"{title}\n{ab.desc}"
            )
        else:
            gate = f"🔒 Lv {need_lv} · {yen_short(cost)}"
            blocks.append(f"{title} — {gate}\n<i>Locked.</i>")
            kb.add(types.InlineKeyboardButton(
                f"🔓 {ab.name} · Lv{need_lv}", callback_data=f"unlock|{ab.id}"
            ))
    kb.row(
        types.InlineKeyboardButton("🔄 Refresh", callback_data=f"kitrefresh|{char_key}"),
        types.InlineKeyboardButton("↩️ Back", callback_data="kitback"),
    )
    slots = db.get_skill_slots(user_id)
    parts = []
    parts.append(RULE)
    parts.append(
        f"⚡ Skill slots — <b>{slots}/{MAX_SKILL_SLOTS}</b> usable per match"
        + ("" if slots >= MAX_SKILL_SLOTS else " · buy the second one:")
    )
    if slots < MAX_SKILL_SLOTS:
        kb.add(types.InlineKeyboardButton(
            f"➕ Second skill slot · {yen_short(SKILL_SLOT_COST)}", callback_data="skillslot"
        ))
    for i, block in enumerate(blocks):
        parts.append(block)
        if i < len(blocks) - 1:
            parts.append(RULE)
    return head + "\n" + "\n".join(x for x in parts if x), kb


BOUND_ROMAN = {1: "I", 2: "II", 3: "III"}


def bound_page(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """🔗 /bind — pick a Bound partner, see the tier, buy upgrades."""
    if not BOUND_ENABLED:
        # test season: Bound exists but stays dormant — show it as inactive
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="bnd|page"))
        text = (
            "🔗 <b>BOUND</b> — ⏸ <b>غیرفعال</b>\n"
            f"{RULE}\n"
            "<i>The Bound system is off for this test season. "
            "Partners, tiers and upgrades will activate when the season starts.</i>"
        )
        return text, kb

    own = db.owned_by(user_id)
    tier = db.get_bound_tier(user_id)
    partner = db.get_bound(user_id)
    row = db.player(user_id)
    level = level_for(row["xp"])
    kb = types.InlineKeyboardMarkup(row_width=1)

    head = f"🔗 <b>BOUND</b> · {icon_of(own['char_key'])}<b>{esc(name_of(own['char_key']))}</b>\n" if own else "🔗 <b>BOUND</b>\n"
    body = [
        f"Tier: <b>Bound {BOUND_ROMAN.get(tier, tier)}</b>"
        + (" · <i>MAX</i>" if tier >= MAX_BOUND_TIER else ""),
    ]
    if partner:
        prow = next((o for o in db.all_owned() if o["char_key"] == partner), None)
        plabel = ""
        if prow:
            p = db.player(prow["user_id"])
            label = (p["display"] or p["username"] or "?") if p else "?"
            plabel = f" · {esc(label)}"
        body.append(f"Partner: {icon_of(partner)}<b>{esc(name_of(partner))}</b>{plabel}")
    else:
        body.append("<i>No partner yet — pick one below.</i>")
    body.append(
        f"{RULE}\n"
        "• Both on the <b>same team</b> in the match → Bound passives work, "
        "any position in the rotation.\n"
        "• One-sided bound → <b>BUFF</b>: both stay inactive.\n"
        "• Tier up <b>replaces</b> the Bound with a stronger one — no switching back."
    )
    if tier < MAX_BOUND_TIER:
        nt = tier + 1
        need_lv = BOUND_TIER_LEVEL.get(nt, 99)
        cost = BOUND_TIER_COST.get(nt, 0)
        locked = level < need_lv
        body.append(
            f"\n🔼 Next: <b>Bound {BOUND_ROMAN[nt]}</b> — numeric effects +{nt - 1} "
            f"· Lv {need_lv} · {yen(cost)}"
        )
        kb.add(types.InlineKeyboardButton(
            ("🔒 " if locked else "🔼 ") + f"Upgrade to Bound {BOUND_ROMAN[nt]} · {yen_short(cost)}",
            callback_data="bnd|up",
        ))
    if partner:
        kb.add(types.InlineKeyboardButton("❌ Clear partner", callback_data="bnd|clear"))
    others = db.all_owned(exclude_user=user_id)
    if others:
        body.append(f"\n{RULE}\n<b>Pick a partner:</b>")
    for o in others[:40]:
        p = db.player(o["user_id"])
        who = (p["display"] or p["username"] or "?") if p else "?"
        label = (f"▸ " if o["char_key"] == partner else "") + \
            f"{icon_of(o['char_key'])} {name_of(o['char_key'])} · {who}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"bnd|set|{o['user_id']}"))
    kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="bnd|page"))
    return head + "\n".join(body), kb


def profile_text(row) -> str:
    own = db.owned_by(row["user_id"])
    level = level_for(row["xp"])
    rname, ricon = rank_for(level)
    career = db.career(row["user_id"])
    w, d, l = db.record(row["user_id"])

    span = max(1, xp_for_level(level + 1) - xp_for_level(level))
    into = max(0, row["xp"] - xp_for_level(level))

    head = f"🎴 <b>{esc(row['display'] or row['username'] or 'Player')}</b>"
    if row["title"]:
        head += f"  <i>«{esc(row['title'])}»</i>"

    if own:
        key = own["char_key"]
        eff = effective_stats(key, json.loads(own["boosts"]))
        body = (
            f"{icon_of(key)}<b>{esc(name_of(key))}</b> · <b>{overall(eff)} OVR</b>\n"
            f"<i>{esc(epithet_of(key))} · {esc(role_of(key))}</i>\n"
            + stat_block(eff)
        )
        entries = kit_entries(row)
        if entries:
            body += f"⚡ {' · '.join(esc(e.split(' ', 1)[1]) for e in entries)}\n"
    else:
        body = "<i>No character yet — /gacha</i>\n"

    medals = db.achievements_of(row["user_id"])
    medal_line = ""
    if medals:
        icons = [economy.medal_label(m["medal"]).split(" ")[0] for m in medals]
        medal_line = f"\n🏅 {' '.join(icons)} ({len(medals)} — /medals)"

    return (
        f"{head}\n" + RULE + "\n" + body + RULE + "\n"
        f"{ricon} <b>{esc(rname)}</b> · Lv <b>{level}</b>\n"
        f"<code>{bar(into, span, 10)}</code> <code>{into}/{span}</code> XP\n"
        + kv_line([("💰", yen_short(row["yen"])), ("⚽", career["goals"]), ("🅰", career["assists"]), ("🧱", career["stops"])]) + "\n"
        f"📊 {career['played']} played · {w}W {d}D {l}L"
        + medal_line
    )


LB_TITLES = {
    "goals": ("⚽", "Top Scorers"),
    "assists": ("🅰", "Top Assists"),
    "stops": ("🧱", "Top Defenders"),
    "yen": ("💰", "Richest"),
    "level": ("🏆", "Highest Level"),
}


def leaderboard_text(field: str) -> str:
    icon, title = LB_TITLES[field]
    rows = db.leaderboard(field)
    if not rows:
        return f"{icon} <b>{title}</b>\n{RULE}\n<i>No entries yet.</i>"

    def value_of(r):
        if field == "yen":
            return yen_short(r["value"])
        if field == "level":
            return f"Lv {level_for(r['value'])}"
        return str(r["value"])

    def name_of_row(r):
        return r["display"] or (f"@{r['username']}" if r["username"] else "?")

    lines = [
        f"{place(i)} {esc(name_of_row(r))} — <b>{value_of(r)}</b>"
        for i, r in enumerate(rows[:10])
    ]
    return f"{icon} <b>{title}</b>\n{HEAVY}\n" + "\n".join(lines)


def leaderboard_keyboard(active: str) -> types.InlineKeyboardMarkup:
    order = ["goals", "assists", "stops", "yen", "level"]
    labels = {"goals": "⚽ Goals", "assists": "🅰 Assists", "stops": "🧱 Stops", "yen": "💰 Rich", "level": "🏆 Level"}
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(*[
        types.InlineKeyboardButton(
            ("▸ " if k == active else "") + labels[k], callback_data=f"lb|{k}"
        )
        for k in order
    ])
    return kb


def card_text(row) -> str:
    own = db.owned_by(row["user_id"])
    level = level_for(row["xp"])
    rname, ricon = rank_for(level)
    career = db.career(row["user_id"])
    name = esc(row["display"] or (f"@{row['username']}" if row["username"] else "Player"))

    head = f"🃏 <b>{name}</b>"
    if not own:
        return f"{head}\n{ricon} Lv {level}\n<i>No character yet.</i>"

    key = own["char_key"]
    eff = effective_stats(key, json.loads(own["boosts"]))
    entries = kit_entries(row)
    kit_line = f"⚡ {' · '.join(esc(e.split(' ', 1)[1]) for e in entries)}\n" if entries else ""
    return (
        f"{head}\n"
        f"{icon_of(key)}<b>{esc(name_of(key))}</b> · <b>{overall(eff)} OVR</b>\n"
        f"<i>«{esc(epithet_of(key))}»</i>\n"
        + stat_block(eff)
        + kit_line + RULE + "\n"
        f"{kv_line([('⚽', career['goals']), ('🅰', career['assists']), ('🧱', career['stops']), ('📊', career['played'])])}\n"
        f"{ricon} {esc(rname)} · Lv <b>{level}</b>"
    )


# ------------------------------------------------------------------ shop (v2)
TITLE_PRESETS = ("The Monster", "Ace Striker", "Blue Lock MVP", "Chosen One", "Devourer")


def next_boost_level(spent: int) -> int:
    return BOOST_LEVELS[min(spent, len(BOOST_LEVELS) - 1)]


def shop_page(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """The whole /shop screen — wallet, character, training grid, store."""
    row = db.player(user_id)
    own = db.owned_by(user_id)
    lines = [
        header("🛒", "SHOP", "Train. Collect. Devour."),
        f"💰 Wallet — <b>{yen(row['yen'])}</b>",
    ]
    kb = types.InlineKeyboardMarkup(row_width=2)
    if own:
        boosts = json.loads(own["boosts"])
        spent = sum(min(MAX_BOOST, boosts.get(s, 0)) for s in STATS)
        allowed = boosts_allowed(level_for(row["xp"]))
        eff = effective_stats(own["char_key"], boosts)
        lines.append(
            f"{icon_of(own['char_key'])}<b>{esc(name_of(own['char_key']))}</b> · <b>{overall(eff)} OVR</b>"
        )
        lines.append(f"💪 Slots <b>{spent}/{allowed}</b> {bar(spent, allowed, 6)}")
        lines += ["", "<b>💪 TRAINING</b>"]
        if spent >= len(BOOST_LEVELS):
            lines.append(hint("All training slots used — level up for more."))
            kb.row(types.InlineKeyboardButton("💪 All slots used ✅", callback_data="noop"))
        else:
            lines.append(hint("Each +1 spends a slot and yen."))
            btns = []
            for s in STATS:
                lvl = min(MAX_BOOST, boosts.get(s, 0))
                if lvl >= MAX_BOOST:
                    btns.append(types.InlineKeyboardButton(
                        f"✅ {STAT_ABBR[s]} MAX", callback_data="noop"))
                elif spent >= allowed:
                    btns.append(types.InlineKeyboardButton(
                        f"🔒 {STAT_ABBR[s]} · Lv{next_boost_level(spent)}", callback_data="noop"))
                else:
                    btns.append(types.InlineKeyboardButton(
                        f"💪 {STAT_ABBR[s]} +1 · {yen(train_cost(lvl))}", callback_data=f"train|{s}"))
            for i in range(0, len(btns), 2):
                kb.row(*btns[i:i + 2])
        if abilities.enabled():
            owned_now = set(abilities.owned_ids(user_id, own["char_key"]))
            locked = [
                ab for ab in abilities.kit_for_char(own["char_key"])
                if ab.id not in owned_now
            ]
            label = (f"⚡ Abilities — {len(locked)} unlock(s) available"
                     if locked else "⚡ Abilities — view kit")
            kb.row(types.InlineKeyboardButton(label, callback_data="openkit"))
    lines += ["", "<b>🎰 STORE</b>",
              hint("Reroll your fate or pick a title.")]
    kb.row(types.InlineKeyboardButton(
        f"🎰 Reroll character — {yen(REROLL_COST)}", callback_data="rollinfo"))
    kb.row(types.InlineKeyboardButton(
        f"🏷 Titles — {yen(TITLE_COST)}", callback_data="titles"))
    return "\n".join(lines), kb


def rollconfirm_page(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """Confirm screen before spending on a reroll — cost, pool, what's lost."""
    row = db.player(user_id)
    own = db.owned_by(user_id)
    cost = REROLL_COST if own else 0
    taken = set(db.taken_keys())
    if own:
        taken.discard(own["char_key"])
    pool = sum(1 for k in ROSTER if k not in taken)
    lines = [
        header("🎰", "REROLL CHARACTER", "One roll. One fate."),
        f"💰 Wallet — <b>{yen(row['yen'])}</b>",
    ]
    if own:
        lines.append(f"♻ Releases <b>{esc(name_of(own['char_key']))}</b>")
    lines += [
        f"🎴 Pool — <b>{pool}</b> characters available",
        (f"Cost — <b>{yen(cost)}</b>" if cost
         else "Cost — <b>FREE 🎁</b> <i>(first pull)</i>"),
        hint("The roll is random — the released character is gone for good."),
    ]
    kb = types.InlineKeyboardMarkup(row_width=1)
    btn = f"✅ Confirm — {yen(cost)}" if cost else "✅ Pull — FREE 🎁"
    kb.row(types.InlineKeyboardButton(btn, callback_data="buyroll"))
    kb.row(types.InlineKeyboardButton("↩️ Back", callback_data="shopback"))
    return "\n".join(lines), kb


def titles_page(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """Title shop — equipped title marked, presets, custom hint."""
    row = db.player(user_id)
    current = row["title"] if "title" in row.keys() else None
    lines = [
        header("🏷", "TITLES", "Shown under your name everywhere."),
        f"💰 Wallet — <b>{yen(row['yen'])}</b>",
        (f"Current — <b>{esc(current)}</b> ✅" if current
         else "Current — <i>none yet</i>"),
        f"Cost — <b>{yen(TITLE_COST)}</b> per title",
        hint("Custom title: /title YourTitle"),
    ]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for title in TITLE_PRESETS:
        if title == current:
            kb.row(types.InlineKeyboardButton(f"✅ {title}", callback_data="noop"))
        else:
            kb.row(types.InlineKeyboardButton(
                f"🏷 {title}", callback_data=f"settitle|{title}"))
    kb.row(types.InlineKeyboardButton("↩️ Back", callback_data="shopback"))
    return "\n".join(lines), kb
