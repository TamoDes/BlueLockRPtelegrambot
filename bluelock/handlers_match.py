import json
import random
import time

from telebot import types

from . import abilities, db, engine, payouts, views
from .characters import effective_stats, name_of
from .config import (
    DICE_ANIM_SECONDS,
    DICE_EMOJI,
    DICE_FACES,
    GOAL_TARGET,
    KEEPER_NAME,
    MATCHLOG_KEEP,
    MODES,
    PENALTY_TARGETS,
    SIZES,
    ZONE_NAME,
)
from .core import (
    NOT_ADMIN,
    NO_CHAR,
    announce_levelups,
    bot,
    broadcast,
    cb_int,
    display_name,
    edit_view,
    is_admin,
    is_pm,
    open_view,
    render_lobby,
    render_match,
    safe,
    seen,
)
from .fmt import RULE, clip, esc

HDR_MATCH = "⚔️ <b>NEW MATCH</b>\n" + RULE
HDR_MATCHES = "📋 <b>ACTIVE MATCHES</b>\n" + RULE


def new_match_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=5)
    for mode, mode_en in MODES.items():
        kb.add(types.InlineKeyboardButton(f"— {mode_en} —", callback_data="noop"))
        kb.add(*[
            types.InlineKeyboardButton(f"{s}v{s}", callback_data=f"new|{mode}|{s}")
            for s in SIZES
        ])
    return kb


@bot.message_handler(commands=["newmatch", "match"])
def newmatch(message):
    seen(message)
    safe(
        bot.reply_to,
        message,
        HDR_MATCH
        + "Pick a format:\n"
        + f"🥇 <b>Ranked</b> — first to {GOAL_TARGET}, full payout\n"
        + "⏱ <b>Friendly</b> — fixed clock, 40%¥ · 60%xp\n"
        + "<i>Others join via /matches from any chat.</i>",
        reply_markup=new_match_keyboard(),
    )


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("new|"))
def new_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 3 or not parts[2].isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    _, mode, size_s = parts
    size = int(size_s)
    if mode not in MODES or size not in SIZES or not call.message:
        safe(bot.answer_callback_query, call.id)
        return

    match_id = db.create_match(call.message.chat.id, mode, size, call.from_user.id)
    match = db.match(match_id)
    sent = safe(
        bot.send_message,
        call.message.chat.id,
        views.lobby_text(match, []),
        reply_markup=views.lobby_keyboard(match, []),
    )
    if sent is None:
        safe(bot.answer_callback_query, call.id, "Couldn't create the lobby.", show_alert=True)
        return
    db.update_match(match_id, message_id=sent.message_id)
    safe(bot.answer_callback_query, call.id, "Lobby created.")
    safe(bot.edit_message_text, "✅ Lobby opened below.", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("join|"))
def join_cb(call):
    seen(call)
    _, mid, team = call.data.split("|")
    match_id, team = int(mid), int(team)

    own = db.owned_by(call.from_user.id)
    if not own:
        safe(bot.answer_callback_query, call.id, NO_CHAR, show_alert=True)
        return

    stats = effective_stats(own["char_key"], json.loads(own["boosts"]))
    name = f"{display_name(call.from_user)} ({name_of(own['char_key']).split()[-1]})"
    result = db.join_match(match_id, team, call.from_user.id, name, own["char_key"], stats)

    toasts = {
        "ok": "✅ You're in.",
        "closed": "This lobby is closed.",
        "already": "You're already in this lobby.",
        "full": "That team is full.",
    }
    safe(bot.answer_callback_query, call.id, toasts[result], show_alert=result != "ok")
    if result == "ok":
        match = db.match(match_id)
        if call.message and call.message.chat.type == "private":
            open_view(match, call.message.chat.id)
        broadcast(match, f"➕ <b>{esc(name)}</b> joined {'🔵 BLUE' if team == 1 else '🔴 RED'}.")
        render_lobby(match_id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("quit|"))
def quit_cb(call):
    seen(call)
    match_id = cb_int(call)
    match = db.match(match_id) if match_id is not None else None
    if not match or match["status"] != "open":
        safe(bot.answer_callback_query, call.id, "Can't leave now.", show_alert=True)
        return
    db.leave_match(match_id, call.from_user.id)
    if call.message and call.message.chat.type == "private":
        db.drop_view(match_id, call.message.chat.id)
    safe(bot.answer_callback_query, call.id, "You left the lobby.")
    render_lobby(match_id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("cancel|"))
def cancel_cb(call):
    seen(call)
    match_id = cb_int(call)
    match = db.match(match_id) if match_id is not None else None
    if not match or match["status"] != "open":
        safe(bot.answer_callback_query, call.id)
        return

    roster = db.roster(match_id)
    starter = match["starter_id"]
    first_player = roster[0]["user_id"] if roster else None
    if not is_admin(call) and call.from_user.id not in {starter, first_player}:
        safe(bot.answer_callback_query, call.id, "Only the lobby starter, a player, or an admin can cancel.", show_alert=True)
        return

    db.update_match(match_id, status="cancelled", ended_at=db.now())
    safe(bot.answer_callback_query, call.id, "Cancelled.")
    edit_view(db.match(match_id), "❌ <b>LOBBY CANCELLED</b>", None)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("kick|"))
def kickoff_cb(call):
    seen(call)
    match_id = cb_int(call)
    if match_id is None or not engine.start(match_id):
        safe(bot.answer_callback_query, call.id, "Teams aren't full yet.", show_alert=True)
        return

    safe(bot.answer_callback_query, call.id, "🟢 Kickoff!")
    render_match(match_id)
    match = db.match(match_id)
    if not is_pm(match) and match["message_id"]:
        safe(bot.pin_chat_message, match["chat_id"], match["message_id"], disable_notification=True)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("menu|"))
def menu_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    _, mid, which = parts
    match_id = int(mid)
    match = db.match(match_id)
    if not match or match["status"] != "live":
        safe(bot.answer_callback_query, call.id, "This match isn't live.", show_alert=True)
        return

    roster = db.roster(match_id)
    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    if holder is None or (holder["user_id"] != call.from_user.id and not is_admin(call)):
        who = esc(holder["name"]) if holder else "?"
        safe(bot.answer_callback_query, call.id, f"Not your turn — the ball is with {who}.", show_alert=True)
        return

    if which == "pass":
        keyboard = views.pass_keyboard(match, roster)
    elif which == "cross":
        keyboard = views.cross_keyboard(match, roster)
    else:
        keyboard = views.action_keyboard(match, roster)
    render_match(match_id, keyboard)
    safe(bot.answer_callback_query, call.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("act|"))
def act_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 4:
        safe(bot.answer_callback_query, call.id)
        return
    _, mid, action, target = parts
    if not mid.lstrip("-").isdigit() or not target.lstrip("-").isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    match_id, target_slot = int(mid), int(target)
    match = db.match(match_id)

    if not match or match["status"] != "live":
        safe(bot.answer_callback_query, call.id, "This match isn't live.", show_alert=True)
        return
    if match["phase"] == "duel":
        safe(bot.answer_callback_query, call.id, "A duel is already in progress — roll your die.", show_alert=True)
        return
    if action not in engine.legal_actions(match):
        reason = engine.illegal_reason(action, engine.zone_of(match)) or "You can't do that right now."
        safe(bot.answer_callback_query, call.id, reason, show_alert=True)
        return

    roster = db.roster(match_id)
    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    if holder is None or (holder["user_id"] != call.from_user.id and not is_admin(call)):
        who = esc(holder["name"]) if holder else "?"
        safe(bot.answer_callback_query, call.id, f"Not your turn — the ball is with {who}.", show_alert=True)
        return

    if action in ("pass", "cross") and target_slot == 0:
        render_match(match_id, views.pass_keyboard(match, roster) if action == "pass" else views.cross_keyboard(match, roster))
        safe(bot.answer_callback_query, call.id, "Pick a receiver.")
        return

    if not db.claim_turn(match_id, match["turn"], holder["slot"]):
        safe(bot.answer_callback_query, call.id, "This turn was already played.", show_alert=True)
        return

    opened = engine.open_duel(match_id, action, target_slot or None)
    if "error" in opened:
        db.release_turn(match_id)
        safe(bot.answer_callback_query, call.id, opened["error"], show_alert=True)
        return

    toast = "🎲 Roll your die!" if not opened.get("notes") else "⚡ Signature move!"
    safe(bot.answer_callback_query, call.id, toast)
    render_match(match_id)
    for line in opened.get("notes", []):
        broadcast(db.match(match_id), line)
        db.log_event(match_id, line)
    advance(match_id)


def spot_keyboard(match_id: int, role: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    icons = {"left": "⬅️", "center": "🎯", "right": "➡️"}
    kb.add(*[
        types.InlineKeyboardButton(
            f"{icons[t]} {t.upper()}", callback_data=f"spot|{match_id}|{role}|{t}"
        )
        for t in PENALTY_TARGETS
    ])
    return kb


def prompt_dice(match_id: int) -> None:
    match = db.match(match_id)
    if not match or match["phase"] != "duel":
        return
    pending = engine.awaiting(match)
    if not pending:
        return

    duel = pending["duel"]
    action = engine.ACTION_NAME[duel["action"]]
    who = esc(pending["name"])
    role = pending["role"]

    if role in ("spot", "spot_gk"):
        for chat_id in broadcast_targets(match):
            label = pending.get("label", "pick")
            suffix = "\n<i>(any defending player may make the call)</i>" if role == "spot_gk" else ""
            safe(
                bot.send_message,
                chat_id,
                f"🎯 <b>{who}</b> — {label}!{suffix}",
                reply_markup=spot_keyboard(match_id, role),
            )
        return

    if role == "att":
        broadcast(match, f"🎲 <b>{who}</b> — <b>{action}</b>! Send a die.")
    else:
        broadcast(match, f"🛡 <b>{who}</b> — roll your defense die.")


def broadcast_targets(match) -> list[int]:
    return list({match["chat_id"], *(r["chat_id"] for r in db.views_of(match["id"]))})


def keeper_roll(match_id: int) -> int:
    match = db.match(match_id)
    sent = safe(bot.send_dice, match["chat_id"], emoji="🎲")
    value = sent.dice.value if sent else random.randint(1, DICE_FACES)
    broadcast(
        match,
        f"🧤 <b>{KEEPER_NAME}</b> comes out — <b>{value}</b>!",
        skip=match["chat_id"] if sent else None,
    )
    return value


def advance(match_id: int) -> None:
    while True:
        match = db.match(match_id)
        if not match or match["phase"] != "duel":
            return

        if not engine.ready(match):
            pending = engine.awaiting(match)
            if pending and pending["role"] == "gk":
                value = keeper_roll(match_id)
                time.sleep(DICE_ANIM_SECONDS)
                fresh = db.match(match_id)
                if not fresh or fresh["phase"] != "duel":
                    return
                if not engine.record_die(match_id, "gk", value):
                    return
                render_match(match_id)
                continue
            stamp_pending_turn(match, engine.pending_of(match))
            render_match(match_id)
            prompt_dice(match_id)
            return

        out = engine.resolve(match_id)
        if out is None:
            return
        text = engine.describe(out, {r["slot"]: r for r in db.roster(match_id)})
        notes = out.get("notes") or []
        full = text + ("\n" + "\n".join(notes) if notes else "")
        db.log_event(match_id, full)
        broadcast(db.match(match_id), full)

        match = db.match(match_id)
        if engine.over(match):
            finish(match_id)
        else:
            stamp_pending_turn(match, engine.pending_of(match))
            render_match(match_id)
        return


def stamp_pending_turn(match, state: dict) -> None:
    stamp = state.get("stamp") or {}
    if stamp.get("turn") == match["turn"] and stamp.get("at"):
        return
    state["stamp"] = {"turn": match["turn"], "at": db.now()}
    db.update_match(match["id"], pending=json.dumps(state))


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("advance|"))
def advance_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    _, mid, turn_s = parts
    match_id, stamped_turn = int(mid), int(turn_s)
    match = db.match(match_id)
    if not match or match["status"] != "live" or match["phase"] != "play":
        safe(bot.answer_callback_query, call.id, "Not right now.", show_alert=True)
        return

    roster = db.roster(match_id)
    holder = next((r for r in roster if r["slot"] == match["holder"]), None)
    if holder is None or (holder["user_id"] != call.from_user.id and not is_admin(call)):
        who = esc(holder["name"]) if holder else "?"
        safe(bot.answer_callback_query, call.id, f"Not your turn — the ball is with {who}.", show_alert=True)
        return

    state = engine.pending_of(match)
    if state.get("set_piece") or state.get("duel"):
        safe(bot.answer_callback_query, call.id, "Not right now.", show_alert=True)
        return
    if engine.marker(roster, holder["team"], state.get("beaten", [])) is not None:
        safe(bot.answer_callback_query, call.id, "You're still marked — dribble or pass instead.", show_alert=True)
        return
    zone = state.get("zone", 0)
    if zone >= engine.ZONE_BOX:
        safe(bot.answer_callback_query, call.id, "Already at the final zone.", show_alert=True)
        return
    if not db.claim_walk(match_id, stamped_turn, holder["slot"]):
        safe(bot.answer_callback_query, call.id, "This turn was already played.", show_alert=True)
        return

    state["zone"] = min(engine.ZONE_BOX, zone + 1)
    state["last_pass"] = None
    state["chain"] = state.get("chain", 0) + 1
    turn = match["turn"] + 1
    db.update_match(match_id, turn=turn, phase="play", pending=json.dumps(state))
    db.bump_slot(match_id, holder["slot"], actions=1)
    line = f"🚶 <b>{esc(holder['name'])}</b> advances unopposed into <b>{ZONE_NAME[state['zone']]}</b>."
    db.log_event(match_id, line)
    match = db.match(match_id)
    if engine.over(match):
        finish(match_id)
    else:
        stamp_pending_turn(match, engine.pending_of(match))
        render_match(match_id)
    safe(bot.answer_callback_query, call.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("spot|"))
def spot_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 4 or not parts[1].lstrip("-").isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    _, mid, role, target = parts
    match_id = int(mid)
    result = engine.submit_spot(match_id, call.from_user.id, target)
    if result["status"] == "wrong":
        safe(bot.answer_callback_query, call.id, f"That's {result['name']}'s call.", show_alert=True)
        return
    if result["status"] != "ok":
        safe(bot.answer_callback_query, call.id)
        return
    safe(bot.answer_callback_query, call.id, f"✅ {target.upper()}")
    hidden = result["role"] == "spot"
    broadcast(
        db.match(match_id),
        f"🎯 <b>{esc(result['name'])}</b> {'locked in a corner' if hidden else 'called ' + target.upper()}",
        skip=call.message.chat.id if call.message else None,
    )
    advance(match_id)


def is_dice(message) -> bool:
    return bool(message.dice and message.dice.emoji in DICE_EMOJI)


@bot.message_handler(content_types=["dice"], func=is_dice)
def dice_thrown(message):
    seen(message)
    match = db.live_duel_in(message.chat.id)
    if not match:
        return

    result = engine.submit_die(match["id"], message.from_user.id, message.dice.value)
    if result["status"] == "wrong":
        label = "🛡 defense" if result["role"] == "def" else "🎲 attack"
        safe(bot.reply_to, message, f"That {label} die belongs to <b>{esc(result['name'])}</b>.")
        return
    if result["status"] != "ok":
        return

    broadcast(
        db.match(match["id"]),
        f"🎲 <b>{esc(result['name'])}</b> rolled <b>{message.dice.value}</b>.",
        skip=message.chat.id,
    )

    time.sleep(DICE_ANIM_SECONDS)
    advance(match["id"])


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("skill|"))
def skill_cb(call):
    seen(call)
    parts = call.data.split("|")
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    _, mid, aid = parts
    match_id = int(mid)
    res = engine.arm_skill(match_id, call.from_user.id, aid)
    alerts = {"swap", "spent", "foreign", "notturn"}
    icon = "🛡" if res.get("kind") == "passive" else "⚡"
    toasts = {
        "armed": f"{icon} {res.get('name')} armed — fires with your next play",
        "disarmed": f"{icon} {res.get('name')} cancelled — charge refunded",
        "swap": f"Already armed: {res.get('name')}. Tap it to cancel first.",
        "spent": "No charges left for that ability this match.",
        "foreign": "That ability belongs to another character.",
        "notturn": "Offensive abilities arm on your own turn — defensive ones (🛡) anytime.",
        "closed": "Not right now.",
        "invalid": "Unknown ability.",
    }
    safe(
        bot.answer_callback_query,
        call.id,
        toasts.get(res["status"], "…"),
        show_alert=res["status"] in alerts,
    )
    if res["status"] in ("armed", "disarmed"):
        ab = abilities.get(aid)
        if ab:
            skill_ctx = views.skill_hint(match_id, call.from_user.id, ab)
            if skill_ctx:
                safe(bot.send_message, call.message.chat.id, skill_ctx)
        render_match(match_id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("flow|"))
def flow_cb(call):
    seen(call)
    match_id = cb_int(call)
    if match_id is None:
        safe(bot.answer_callback_query, call.id)
        return
    res = engine.activate_flow(match_id, call.from_user.id)
    toasts = {
        "ok": "🔥🔥 FLOW STATE!",
        "notready": "Your FLOW isn't ready yet — win more duels.",
        "duel": "Wait — a duel is being resolved.",
        "foreign": "You're not in this match.",
        "closed": "Not right now.",
    }
    safe(bot.answer_callback_query, call.id, toasts.get(res["status"], "…"), show_alert=res["status"] != "ok")
    if res["status"] == "ok":
        broadcast(db.match(match_id), res["line"])
        render_match(match_id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("undo|"))
def undo_cb(call):
    seen(call)
    match_id = cb_int(call)
    match = db.match(match_id) if match_id is not None else None
    if not match or match["phase"] != "duel":
        safe(bot.answer_callback_query, call.id, "Nothing to cancel.")
        return

    pending = engine.awaiting(match)
    allowed = {pending["user_id"]} if pending and pending["user_id"] else set()
    if call.from_user.id not in allowed and not is_admin(call):
        safe(bot.answer_callback_query, call.id, "Only the roller or an admin.", show_alert=True)
        return

    engine.cancel_duel(match_id)
    safe(bot.answer_callback_query, call.id, "Action cancelled.")
    render_match(match_id)


def finish(match_id: int) -> None:
    settled = payouts.settle(match_id)
    if settled is None:
        return
    report, level_ups = settled
    match = db.match(match_id)
    render_match(match_id, types.InlineKeyboardMarkup())
    if not is_pm(match) and match["message_id"]:
        safe(bot.unpin_chat_message, match["chat_id"], match["message_id"])
    broadcast(match, report)
    for chat_id in {match["chat_id"]} | {r["chat_id"] for r in db.views_of(match_id)}:
        announce_levelups(chat_id, level_ups)


def do_surrender(match, roster, me) -> None:
    field = "score1" if me["team"] == 1 else "score2"
    opponent = "score2" if me["team"] == 1 else "score1"
    state = engine.pending_of(match)
    state.pop("duel", None)
    state.pop("notes", None)
    db.update_match(match["id"], pending=json.dumps(state), **{field: 0, opponent: match[opponent] + 1})
    broadcast(match, f"🏳️ <b>{esc(me['name'])}</b> surrendered! Final: {match[opponent] + 1} — 0")
    finish(match["id"])


def surrender_check(event, match) -> tuple[list, dict] | str:
    if not match or match["status"] != "live":
        return "No live match here."
    roster = db.roster(match["id"])
    me = next((r for r in roster if r["user_id"] == event.from_user.id), None)
    if not me:
        return "You're not in this match."
    captain = min((r for r in roster if r["team"] == me["team"]), key=lambda r: r["slot"])
    if me["slot"] != captain["slot"] and not is_admin(event):
        return f"Only the captain (<b>{esc(captain['name'])}</b>) can surrender."
    return roster, me


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("surrender|"))
def surrender_cb(call):
    seen(call)
    mid = cb_int(call)
    match = db.match(mid) if mid is not None else None
    checked = surrender_check(call, match)
    if isinstance(checked, str):
        safe(bot.answer_callback_query, call.id, checked, show_alert=True)
        return
    safe(bot.answer_callback_query, call.id, "🏳️ Surrendered.")
    do_surrender(match, *checked)


@bot.message_handler(commands=["surrender", "ff", "concede"])
def surrender_cmd(message):
    seen(message)
    match = db.match_of_user(message.from_user.id)
    checked = surrender_check(message, match)
    if isinstance(checked, str):
        safe(bot.reply_to, message, checked)
        return
    do_surrender(match, *checked)


@bot.message_handler(commands=["forcefinish"])
def forcefinish(message):
    seen(message)
    if not is_admin(message):
        safe(bot.reply_to, message, NOT_ADMIN)
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        safe(bot.reply_to, message, "Usage: <code>/forcefinish 12</code> (ID from /matches)")
        return
    match_id = int(parts[1].lstrip("#"))
    match = db.match(match_id)
    if not match or match["status"] != "live":
        safe(bot.reply_to, message, "No active match with that ID.")
        return
    finish(match_id)
    safe(bot.reply_to, message, f"🏁 Match #{match_id} closed.")


@bot.message_handler(commands=["matches"])
def matches_cmd(message):
    seen(message)
    rows = db.open_matches()
    if not rows:
        safe(bot.reply_to, message, "No active matches. Start one with /newmatch.")
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    lines = []
    for r in rows[:10]:
        roster = db.roster(r["id"])
        c1 = sum(1 for x in roster if x["team"] == 1)
        c2 = sum(1 for x in roster if x["team"] == 2)
        live = r["status"] == "live"
        lines.append(
            f"{'🟢' if live else '🕓'} <code>#{r['id']}</code> {MODES.get(r['mode'], r['mode'])} "
            f"{r['size']}v{r['size']} — "
            + (f"<b>{r['score1']}-{r['score2']}</b>" if live else f"{c1 + c2}/{r['size'] * 2} players")
        )
        label = f"{'👀 Watch' if live else '⚔️ Open'} #{r['id']} · {r['size']}v{r['size']}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"open|{r['id']}"))

    safe(bot.reply_to, message, HDR_MATCHES + "\n".join(lines), reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("open|"))
def open_cb(call):
    seen(call)
    match_id = cb_int(call)
    match = db.match(match_id) if match_id is not None else None
    if not match or match["status"] not in ("open", "live"):
        safe(bot.answer_callback_query, call.id, "That match is over.", show_alert=True)
        return
    if not call.message:
        safe(bot.answer_callback_query, call.id, "Use /matches here to open it.", show_alert=True)
        return
    if open_view(match, call.message.chat.id):
        safe(bot.answer_callback_query, call.id, "Opened below 👇")
    else:
        safe(
            bot.answer_callback_query,
            call.id,
            "Can't post here — add me to this group and let me send messages.",
            show_alert=True,
        )


@bot.message_handler(commands=["matchlog"])
def matchlog_cmd(message):
    seen(message)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        safe(bot.reply_to, message, "Usage: <code>/matchlog 12</code> (ID from /matches)")
        return
    match_id = int(parts[1].lstrip("#"))
    match = db.match(match_id)
    if not match:
        safe(bot.reply_to, message, "No match with that ID.")
        return
    rows = db.q(
        "SELECT seq, text FROM events WHERE match_id=? ORDER BY seq DESC LIMIT ?",
        (match_id, MATCHLOG_KEEP),
    )
    if not rows:
        safe(bot.reply_to, message, f"Match #{match_id} has no logged events yet.")
        return
    total = db.q1("SELECT COUNT(*) AS n FROM events WHERE match_id=?", (match_id,))["n"]
    head = (
        f"📜 <b>MATCH LOG · #{match_id}</b>\n"
        f"{MODES.get(match['mode'], match['mode'])} {match['size']}v{match['size']} · "
        f"🔵 {match['score1']} — {match['score2']} 🔴 · {match['status']}\n{RULE}\n"
    )
    tail = f"\n<i>… last {len(rows)} of {total} plays.</i>" if total > len(rows) else ""
    lines = [f"{r['seq']}. {clip(r['text'], 70)}" for r in reversed(rows)]
    chunks = [head]
    for line in lines:
        if len(chunks[-1]) + len(line) + 1 > 3800:
            chunks.append("")
        chunks[-1] += line + "\n"
    for i, chunk in enumerate(chunks):
        text = chunk if i == 0 else f"📜 <b>MATCH LOG · #{match_id} (cont.)</b>\n{RULE}\n{chunk}"
        safe(bot.send_message, message.chat.id, text.rstrip() + (tail if i == len(chunks) - 1 else ""))


@bot.callback_query_handler(func=lambda c: c.data == "rulesbtn")
def rules_btn_cb(call):
    seen(call)
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(bot.send_message, call.message.chat.id, views.rules_text())


def relayable(message) -> bool:
    return (
        message.chat.type == "private"
        and bool(message.text)
        and not message.text.startswith("/")
    )


@bot.message_handler(func=relayable, content_types=["text"])
def relay_chat(message):
    seen(message)
    match = db.match_of_user(message.from_user.id)
    if not match:
        return
    roster = db.roster(match["id"])
    me = next((r for r in roster if r["user_id"] == message.from_user.id), None)
    if me is None:
        return
    icon = "🔵" if me["team"] == 1 else "🔴"
    broadcast(
        match,
        f"{icon} <b>{esc(me['name'])}:</b> {esc(message.text[:400])}",
        skip=message.chat.id,
    )
