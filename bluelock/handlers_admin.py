import json
import re

from telebot import types

from . import abilities, db, engine, payouts
from .characters import ROSTER, effective_stats, icon_of, name_of, overall, resolve, role_of
from .config import (
    MAX_LEVEL,
    MODES,
    STATS,
    STAT_ABBR,
    ZONE_NAME,
    level_for,
    xp_for_level,
)
from .core import NOT_ADMIN, bot, is_admin, safe, seen
from .fmt import RULE, esc, yen, yen_short

PAGE = 8
PER_TX = 5


def admin_guard(fn):
    def wrapper(event, *args, **kwargs):
        seen(event)
        if not is_admin(event):
            if getattr(event, "message", None):
                safe(bot.reply_to, event.message, NOT_ADMIN)
            return
        return fn(event, *args, **kwargs)
    return wrapper


def player_label(row) -> str:
    name = row["display"] or (f"@{row['username']}" if row["username"] else f"ID{row['user_id']}")
    return esc(name)


def own_line(user_id: int) -> str:
    own = db.owned_by(user_id)
    if not own:
        return "🆓 <i>No character</i>"
    key = own["char_key"]
    eff = effective_stats(key, json.loads(own["boosts"]))
    return f"{icon_of(key)}<b>{esc(name_of(key))}</b> · {overall(eff)} OVR"


def back_kb(target: str, mid: int | None = None) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩︎ Back", callback_data=f"adm|{target}|{mid if mid is not None else 0}|0"))
    return kb


# ------------------------------------------------------------------ /admin hub

@admin_guard
def admin_cmd(message):
    text, kb = hub_panel(0, 0)
    safe(bot.reply_to, message, text, reply_markup=kb)


@bot.message_handler(commands=["admin", "panel"])
def admin_entry(message):
    admin_cmd(message)


# ------------------------------------------------------------------ navigation

RENDERERS: dict[str, object] = {}
ACTIONS: dict[str, object] = {}
NAV_TO: dict[str, str] = {}


def reg(target: str):
    def deco(fn):
        RENDERERS[target] = fn
        return fn
    return deco


def action(target: str, nav_to: str):
    def deco(fn):
        ACTIONS[target] = fn
        NAV_TO[target] = nav_to
        return fn
    return deco


@reg("hub")
def hub_panel(ctx: int, page: int):
    row = db.stat_summary()
    text = (
        "🛠 <b>ADMIN PANEL</b>\n" + RULE + "\n"
        f"👥 {row['players']} players · 🃏 {row['chars']} chars\n"
        f"💰 Σ{yen_short(row['yen'])} in wallets · {row['unlocks']} unlocks\n"
        f"⚔️ {row['open']} open · 🟢 {row['live']} live · Σ{row['matches_total']} matches\n"
        + RULE
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 Players", callback_data="adm|players|0|0"),
        types.InlineKeyboardButton("⚔️ Matches", callback_data="adm|matches|0|0"),
    )
    kb.add(
        types.InlineKeyboardButton("🎮 Match Control", callback_data="adm|mctl|0|0"),
        types.InlineKeyboardButton("💰 Wallet", callback_data="adm|wallet|0|0"),
    )
    kb.add(
        types.InlineKeyboardButton("🃏 Characters", callback_data="adm|chars|0|0"),
        types.InlineKeyboardButton("⚡ Abilities", callback_data="adm|abilities|0|0"),
    )
    kb.add(
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm|broadcast|0|0"),
        types.InlineKeyboardButton("⚙️ Engine / Config", callback_data="adm|config|0|0"),
    )
    return text, kb


def render(target: str, ctx: int, page: int):
    fn = RENDERERS.get(target)
    if fn is None:
        return None, None
    return fn(ctx, page)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("adm|"))
def adm_nav(call):
    seen(call)
    parts = call.data.split("|")
    if not is_admin(call):
        safe(bot.answer_callback_query, call.id, NOT_ADMIN, show_alert=True)
        return
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        safe(bot.answer_callback_query, call.id)
        return
    target, ctx, page = parts[1], int(parts[2]), 0
    if len(parts) >= 4 and parts[3].lstrip("-").isdigit():
        page = int(parts[3])
    if target == "noop":
        safe(bot.answer_callback_query, call.id)
        return

    action = ACTIONS.get(target)
    if action is not None:
        ok, toast = action(call, ctx)
        if toast is None and not ok:
            return
        safe(bot.answer_callback_query, call.id, toast or "✅", show_alert=not ok)
        if not call.message:
            return
        if not ok:
            return
        text, kb = render(NAV_TO.get(target, "hub"), ctx, page)
        if text is not None:
            safe(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    text, kb = render(target, ctx, page)
    if text is None:
        safe(bot.answer_callback_query, call.id, "Unknown panel.", show_alert=True)
        return
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=kb)


def pager(target: str, ctx: int, page: int, total: int) -> types.InlineKeyboardMarkup | None:
    kb = types.InlineKeyboardMarkup()
    if total > PAGE:
        row = []
        if page > 0:
            row.append(types.InlineKeyboardButton("◀️", callback_data=f"adm|{target}|{ctx}|{page - 1}"))
        row.append(types.InlineKeyboardButton(f"{page + 1}/{(total + PAGE - 1) // PAGE}", callback_data="adm|noop|0|0"))
        if (page + 1) * PAGE < total:
            row.append(types.InlineKeyboardButton("▶️", callback_data=f"adm|{target}|{ctx}|{page + 1}"))
        kb.row(*row)
    return kb


# ------------------------------------------------------------------ players list

@reg("players")
def players_panel(ctx: int, page: int):
    total = db.count_players()
    rows = db.players_page(page * PAGE, PAGE)
    kb = pager("players", ctx, page, total) or types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔎 Search by name", callback_data="adm|psearch|0|0"))
    lines = []
    for r in rows:
        own = db.owned_by(r["user_id"])
        char = f" · {name_of(own['char_key']).split()[-1]}" if own else ""
        label = r["display"] or (f"@{r['username']}" if r["username"] else f"ID{r['user_id']}")
        lines.append(f"• <b>{esc(label)}</b> · Lv{level_for(r['xp'])} · {yen_short(r['yen'])}{char}")
    text = (
        f"👥 <b>PLAYERS</b> ({total})\n{RULE}\n"
        + ("\n".join(lines) if lines else "<i>— empty —</i>")
    )
    for r in rows[:PAGE]:
        label = r["display"] or (f"@{r['username']}" if r["username"] else f"ID{r['user_id']}")
        kb.add(types.InlineKeyboardButton(f"🎛 {label}", callback_data=f"adm|player|{r['user_id']}|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@reg("psearch")
def psearch_panel(ctx: int, page: int):
    text = (
        "🔎 <b>PLAYER SEARCH</b>\n" + RULE + "\n"
        "Reply to this message with:\n<code>/afind name</code>"
    )
    kb = back_kb("players")
    return text, kb


@bot.message_handler(commands=["afind"])
@admin_guard
def afind_cmd(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe(bot.reply_to, message, "Usage: <code>/afind name</code>")
        return
    rows = db.players_page(0, PAGE, parts[1].strip())
    if not rows:
        safe(bot.reply_to, message, "No player matched.")
        return
    kb = types.InlineKeyboardMarkup()
    lines = []
    for r in rows:
        label = r["display"] or (f"@{r['username']}" if r["username"] else f"ID{r['user_id']}")
        lines.append(f"• <b>{esc(label)}</b> · Lv{level_for(r['xp'])} · {yen_short(r['yen'])}")
        kb.add(types.InlineKeyboardButton(f"🎛 {label}", callback_data=f"adm|player|{r['user_id']}|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Players", callback_data="adm|players|0|0"))
    safe(bot.reply_to, message, f"🔎 <b>MATCHES</b>\n{RULE}\n" + "\n".join(lines), reply_markup=kb)


# ------------------------------------------------------------------ player control

@reg("player")
def player_panel(user_id: int, page: int):
    row = db.player(user_id)
    if row is None:
        return f"❔ Player <code>{user_id}</code> not found.", back_kb("players")
    w, d, l = db.record(user_id)
    career = db.career(user_id)
    unlocks = db.unlocked_ids(user_id)

    text = (
        f"🎛 <b>PLAYER CONTROL</b>\n{RULE}\n"
        f"<b>{player_label(row)}</b> · <code>{user_id}</code>\n"
        f"{own_line(user_id)}\n"
        f"Lv <b>{level_for(row['xp'])}</b> · {row['xp']}xp · 💰 {yen_short(row['yen'])}\n"
        f"Title: <i>{esc(row['title']) if row['title'] else '—'}</i>\n"
        f"📊 {career['played']}g {w}W {d}D {l}L · ⚽{career['goals']} 🅰{career['assists']} 🧱{career['stops']}\n"
        f"⚡ Unlocks: {len(unlocks)}\n"
        + RULE
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💰 Yen", callback_data=f"adm|pyen|{user_id}|0"),
        types.InlineKeyboardButton("📈 XP", callback_data=f"adm|pxp|{user_id}|0"),
    )
    kb.add(
        types.InlineKeyboardButton("🃏 Character", callback_data=f"adm|pchar|{user_id}|0"),
        types.InlineKeyboardButton("⚡ Unlocks", callback_data=f"adm|punlock|{user_id}|0"),
    )
    kb.add(
        types.InlineKeyboardButton("🏷 Title", callback_data=f"adm|ptitle|{user_id}|0"),
        types.InlineKeyboardButton("💳 Transactions", callback_data=f"adm|ptx|{user_id}|0"),
    )
    kb.add(
        types.InlineKeyboardButton("⚔️ Current match", callback_data=f"adm|pmatch|{user_id}|0"),
        types.InlineKeyboardButton("🚫 Reset boosts", callback_data=f"adm|pboost|{user_id}|0"),
    )
    kb.add(types.InlineKeyboardButton("🗑 DELETE ACCOUNT", callback_data=f"adm|pdelask|{user_id}|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Players", callback_data="adm|players|0|0"))
    return text, kb


@reg("pdelask")
def pdelask_panel(user_id: int, page: int):
    row = db.player(user_id)
    if row is None:
        return "❔ Player not found.", back_kb("players")
    own = db.owned_by(user_id)
    m = db.match_of_user(user_id)
    warn = (
        f"🗑 <b>DELETE ACCOUNT</b>\n{RULE}\n"
        f"<b>{player_label(row)}</b> · <code>{user_id}</code>\n"
        f"This WIPES: player row, yen ({yen_short(row['yen'])}), xp, title, character"
        f"{f' ({name_of(own['char_key'])})' if own else ''}, unlocks, transaction history.\n"
    )
    if m:
        warn += f"⚠️ They are in live match #{m['id']} — it will be cancelled too.\n"
    warn += RULE + "\n<i>This cannot be undone.</i>"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💣 CONFIRM DELETE", callback_data=f"adm|pdel|{user_id}|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Cancel", callback_data=f"adm|player|{user_id}|0"))
    return warn, kb


@action("pdel", "players")
def act_pdel(call, user_id):
    row = db.player(user_id)
    if row is None:
        return False, "Already gone."
    if not db.delete_player(user_id):
        return False, "Delete failed."
    safe(bot.send_message, call.message.chat.id, f"🗑 <b>{player_label(row)}</b> (<code>{user_id}</code>) wiped from the database.")
    return True, "🗑 Account deleted."


@action("pyen", "player")
def act_pyen(call, user_id):
    row = db.player(user_id)
    if row is None:
        return False, "Player gone."
    amount = parse_amount(call.data)
    if amount is None:
        return False, None
    total = db.add_yen(user_id, amount, f"admin @{call.from_user.username}")
    return True, f"💰 {'+' if amount >= 0 else ''}{yen_short(amount)} → {yen_short(total)}"


@action("pxp", "player")
def act_pxp(call, user_id):
    row = db.player(user_id)
    if row is None:
        return False, "Player gone."
    amount = parse_amount(call.data)
    if amount is None:
        return False, None
    db.add_xp(user_id, amount)
    return True, f"📈 {'+' if amount >= 0 else ''}{amount}xp → Lv {level_for(db.player(user_id)['xp'])}"


@action("pboost", "player")
def act_pboost(call, user_id):
    own = db.owned_by(user_id)
    if not own:
        return False, "No character to reset."
    db.set_boosts(user_id, {})
    return True, "💪 Boosts reset to zero."


AMOUNTS = (500_000, 1_000_000, 5_000_000, -500_000)


def parse_amount(call_data: str) -> int | None:
    parts = call_data.split("|")
    if len(parts) >= 4 and parts[3].lstrip("-").isdigit():
        return int(parts[3])
    return None


def amount_kb(prefix: str, user_id: int, amounts=AMOUNTS) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    for a in amounts:
        kb.add(types.InlineKeyboardButton(
            f"{'➕' if a >= 0 else '➖'} {yen_short(abs(a))}",
            callback_data=f"adm|{prefix}|{user_id}|{a}",
        ))
    return kb


@reg("pyen")
def pyen_panel(user_id: int, page: int):
    row = db.player(user_id)
    if row is None:
        return "❔ Player not found.", back_kb("players")
    kb = amount_kb("pyen", user_id)
    kb.add(types.InlineKeyboardButton("✏️ Custom: /ayen ID ±amount", callback_data="adm|noop|0|0"))
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return f"💰 <b>YEN — {player_label(row)}</b>\nBalance: <b>{yen(row['yen'])}</b>", kb


@reg("pxp")
def pxp_panel(user_id: int, page: int):
    row = db.player(user_id)
    if row is None:
        return "❔ Player not found.", back_kb("players")
    kb = amount_kb("pxp", user_id, (100, 260, 1000, -260))
    kb.add(types.InlineKeyboardButton("✏️ Custom: /axp ID ±amount", callback_data="adm|noop|0|0"))
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return f"📈 <b>XP — {player_label(row)}</b>\nTotal: <b>{row['xp']}xp</b> · Lv {level_for(row['xp'])}", kb


@reg("ptitle")
def ptitle_panel(user_id: int, page: int):
    row = db.player(user_id)
    if row is None:
        return "❔ Player not found.", back_kb("players")
    kb = types.InlineKeyboardMarkup()
    if row["title"]:
        kb.add(types.InlineKeyboardButton("🗑 Clear title", callback_data=f"adm|ptitleclr|{user_id}|0"))
    kb.add(types.InlineKeyboardButton("✏️ Set: /atitle ID text", callback_data="adm|noop|0|0"))
    kb.add(back_kb("player", user_id).keyboard[0][0])
    cur = esc(row["title"]) if row["title"] else "—"
    return f"🏷 <b>TITLE — {player_label(row)}</b>\nCurrent: <i>{cur}</i>", kb


@action("ptitleclr", "player")
def act_ptitleclr(call, user_id):
    db.set_title(user_id, None)
    return True, "🏷 Title cleared."


@reg("ptx")
def ptx_panel(user_id: int, page: int):
    rows = db.q(
        "SELECT amount, reason, created_at FROM wallet_tx WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
        (user_id, PAGE, page * PAGE),
    )
    total = db.q1("SELECT COUNT(*) AS n FROM wallet_tx WHERE user_id=?", (user_id,))["n"]
    lines = [
        f" {'🟢' if t['amount'] > 0 else '🔴'} {t['amount']:+,} — <i>{esc(t['reason'])}</i>"
        for t in rows
    ] or ["<i>— none —</i>"]
    kb = pager("ptx", user_id, page, total) or types.InlineKeyboardMarkup()
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return f"💳 <b>TRANSACTIONS</b> ({total})\n{RULE}\n" + "\n".join(lines), kb


@reg("punlock")
def punlock_panel(user_id: int, page: int):
    own = db.owned_by(user_id)
    if not own:
        return "🆓 <i>No character — nothing to unlock.</i>", back_kb("player", user_id)
    key = own["char_key"]
    owned = db.unlocked_ids(user_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    lines = []
    for ab in abilities.kit_for_char(key):
        mark = "✅" if ab.id in owned or ab.tier == 1 else "🔒"
        lines.append(f"{mark} {ab.name}")
        if ab.tier > 1:
            if ab.id in owned:
                kb.add(types.InlineKeyboardButton(f"↩︎ Revoke {ab.name}", callback_data=f"adm|punrev|{user_id}|0|{ab.id}"))
            else:
                kb.add(types.InlineKeyboardButton(f"🔓 Grant {ab.name}", callback_data=f"adm|pugrant|{user_id}|0|{ab.id}"))
    kb.add(types.InlineKeyboardButton("⭐ Grant ALL", callback_data=f"adm|pugrant|{user_id}|0|ALL"))
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return f"⚡ <b>UNLOCKS — {esc(name_of(key))}</b>\n{RULE}\n" + "\n".join(lines), kb


@action("pugrant", "punlock")
def act_pugrant(call, user_id):
    own = db.owned_by(user_id)
    if not own:
        return False, "No character."
    aid = call.data.split("|")[4] if len(call.data.split("|")) > 4 else "ALL"
    if aid == "ALL":
        n = db.grant_all_unlocks(user_id, own["char_key"])
        return True, f"⭐ Granted {n} unlock(s)."
    ab = abilities.get(aid)
    if ab is None:
        return False, "Unknown ability."
    db.grant_unlock(user_id, aid)
    return True, f"🔓 {ab.name} granted."


@action("punrev", "punlock")
def act_punrev(call, user_id):
    parts = call.data.split("|")
    aid = parts[4] if len(parts) > 4 else ""
    ab = abilities.get(aid)
    if ab is None:
        return False, "Unknown ability."
    if db.revoke_unlock(user_id, aid):
        return True, f"↩︎ {ab.name} revoked."
    return False, "Wasn't unlocked."


@reg("pchar")
def pchar_panel(user_id: int, page: int):
    own = db.owned_by(user_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    taken = db.taken_keys()
    if own:
        taken.discard(own["char_key"])
        cur = f"{icon_of(own['char_key'])}{name_of(own['char_key'])}"
        boosts = json.loads(own["boosts"])
        boost_str = " ".join(f"{STAT_ABBR[s]}+{boosts[s]}" for s in STATS if boosts.get(s)) or "none"
        text = (
            f"🃏 <b>CHARACTER — {cur}</b>\n"
            f"Boosts: <i>{boost_str}</i>\n"
            f"<i>Reassigning releases the old character (boosts lost, unlocks stay).</i>"
        )
        kb.add(types.InlineKeyboardButton("♻️ Release (no reassign)", callback_data=f"adm|pcharrel|{user_id}|0"))
    else:
        text = "🃏 <b>CHARACTER</b>\n<i>No character — assign one below.</i>"
    free = [k for k in ROSTER if k not in taken]
    for key in free:
        kb.add(types.InlineKeyboardButton(
            f"{icon_of(key)}{name_of(key)}", callback_data=f"adm|pcharset|{user_id}|0|{key}"
        ))
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return text, kb


@action("pcharset", "player")
def act_pcharset(call, user_id):
    parts = call.data.split("|")
    key = parts[4] if len(parts) > 4 else ""
    if key not in ROSTER:
        return False, "Unknown character."
    if db.owned_by(user_id) is None:
        db.force_assign_char(user_id, key)
        return True, f"🃏 {name_of(key)} assigned."
    taken = db.taken_keys()
    own = db.owned_by(user_id)
    taken.discard(own["char_key"])
    if key in taken:
        return False, "That character is already taken."
    db.force_assign_char(user_id, key)
    return True, f"🃏 Reassigned to {name_of(key)}."


@action("pcharrel", "player")
def act_pcharrel(call, user_id):
    own = db.owned_by(user_id)
    if not own:
        return False, "No character."
    db.force_release_char(user_id)
    return True, f"♻️ {name_of(own['char_key'])} released."


@reg("pmatch")
def pmatch_panel(user_id: int, page: int):
    m = db.match_of_user(user_id)
    if not m:
        return "⚔️ <i>Player is in no open/live match.</i>", back_kb("player", user_id)
    roster = db.roster(m["id"])
    lines = [
        f"{'🟢' if r['team'] == 1 else '🔴'} {r['name']}" for r in roster
    ]
    text = (
        f"⚔️ <b>MATCH #{m['id']}</b> — {MODES.get(m['mode'], m['mode'])} {m['size']}v{m['size']}\n"
        f"Status: <b>{m['status']}</b> · Score {m['score1']}-{m['score2']} · Turn {m['turn']}\n{RULE}\n"
        + "\n".join(lines)
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏁 Force finish", callback_data=f"adm|mfinish|{m['id']}|0"),
        types.InlineKeyboardButton("❌ Cancel", callback_data=f"adm|mforcecancel|{m['id']}|0"),
    )
    kb.add(
        types.InlineKeyboardButton("🔁 Reset duel", callback_data=f"adm|mreset|{m['id']}|0"),
        types.InlineKeyboardButton("➡️ Pass ball to…", callback_data=f"adm|mball|{m['id']}|0"),
    )
    kb.add(back_kb("player", user_id).keyboard[0][0])
    return text, kb


# ------------------------------------------------------------------ matches list

@reg("matches")
def matches_panel(ctx: int, page: int):
    total = db.count_matches()
    rows = db.matches_page(page * PAGE, PAGE)
    icons = {"open": "🕓", "live": "🟢", "done": "🏁", "cancelled": "❌"}
    lines = [
        f"{icons.get(r['status'], '·')} <code>#{r['id']}</code> {MODES.get(r['mode'], r['mode'])} "
        f"{r['size']}v{r['size']} · {r['status']} · {r['score1']}-{r['score2']}"
        for r in rows
    ]
    kb = pager("matches", ctx, page, total) or types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(
            f"🎛 #{r['id']} · {r['status']}", callback_data=f"adm|match|{r['id']}|0"
        ))
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return f"⚔️ <b>MATCHES</b> ({total})\n{RULE}\n" + ("\n".join(lines) if lines else "<i>— none —</i>"), kb


@reg("match")
def match_panel(match_id: int, page: int):
    m = db.match(match_id)
    if not m:
        return f"❔ Match #{match_id} not found.", back_kb("matches")
    roster = db.roster(match_id)
    state = engine.pending_of(m)
    holder = next((r["name"] for r in roster if r["slot"] == m["holder"]), "—")
    text = (
        f"⚔️ <b>MATCH #{m['id']}</b>\n{RULE}\n"
        f"{MODES.get(m['mode'], m['mode'])} {m['size']}v{m['size']} · chat <code>{m['chat_id']}</code>\n"
        f"Status <b>{m['status']}</b> · phase <b>{m['phase']}</b> · turn {m['turn']}\n"
        f"🔵 {m['score1']} — {m['score2']} 🔴 · ball: <b>{esc(holder)}</b>\n"
        f"zone: {ZONE_NAME[state.get('zone', 0)] if state.get('zone', 0) < len(ZONE_NAME) else '?'}"
        + (f" · set piece: <b>{state['set_piece']}</b>" if state.get("set_piece") else "")
        + ("\n🆚 <i>duel in progress</i>" if state.get("duel") else "")
        + "\n" + RULE + "\n"
    )
    text += "\n".join(
        f"{'🟢' if r['team'] == 1 else '🔴'} {r['name']} ⚽{r['goals']} 🅰{r['assists']} 🧱{r['stops']}"
        for r in roster
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    if m["status"] == "live":
        kb.add(types.InlineKeyboardButton("🏁 Force finish", callback_data=f"adm|mfinish|{match_id}|0"))
        kb.add(types.InlineKeyboardButton("❌ Cancel (no payout)", callback_data=f"adm|mforcecancel|{match_id}|0"))
        kb.add(types.InlineKeyboardButton("🔁 Reset duel", callback_data=f"adm|mreset|{match_id}|0"))
        kb.add(types.InlineKeyboardButton("➡️ Pass ball", callback_data=f"adm|mball|{match_id}|0"))
        kb.add(types.InlineKeyboardButton("👁 Publish here", callback_data=f"adm|mview|{match_id}|0"))
    elif m["status"] == "open":
        kb.add(types.InlineKeyboardButton("❌ Cancel lobby", callback_data=f"adm|mforcecancel|{match_id}|0"))
        kb.add(types.InlineKeyboardButton("🟢 Force kickoff", callback_data=f"adm|mkick|{match_id}|0"))
    else:
        kb.add(types.InlineKeyboardButton("🏆 Re-settle payouts", callback_data=f"adm|mresettle|{match_id}|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Matches", callback_data="adm|matches|0|0"))
    return text, kb


@action("mfinish", "match")
def act_mfinish(call, match_id):
    m = db.match(match_id)
    if not m or m["status"] != "live":
        return False, "Not live."
    from .handlers_match import finish
    finish(match_id)
    return True, "🏁 Settled and closed."


@action("mforcecancel", "match")
def act_mforcecancel(call, match_id):
    m = db.match(match_id)
    if not m or m["status"] not in ("open", "live"):
        return False, "Not active."
    db.update_match(match_id, status="cancelled", phase="done", ended_at=db.now())
    from .core import edit_view
    edit_view(db.match(match_id), "🛑 <b>MATCH CANCELLED</b> (admin)", None)
    return True, "🛑 Cancelled."


@action("mkick", "match")
def act_mkick(call, match_id):
    if not engine.start(match_id):
        return False, "Teams aren't full."
    return True, "🟢 Kickoff forced."


@action("mreset", "match")
def act_mreset(call, match_id):
    m = db.match(match_id)
    if not m or m["phase"] != "duel":
        return False, "No duel in progress."
    engine.cancel_duel(match_id)
    from .core import render_match
    render_match(match_id)
    return True, "🔁 Duel reset — turn back to holder."


@reg("mball")
def mball_panel(match_id: int, page: int):
    m = db.match(match_id)
    if not m:
        return "❔ Match gone.", back_kb("matches")
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in db.roster(match_id):
        mark = "▸" if r["slot"] == m["holder"] else ""
        kb.add(types.InlineKeyboardButton(
            f"{'🔵' if r['team'] == 1 else '🔴'}{mark}{r['name']}",
            callback_data=f"adm|msetslot|{match_id}|0|{r['slot']}",
        ))
    kb.add(back_kb("match", match_id).keyboard[0][0])
    return "➡️ <b>PASS BALL TO</b>", kb


@action("msetslot", "mball")
def act_msetslot(call, match_id):
    parts = call.data.split("|")
    if len(parts) < 5 or not parts[4].isdigit():
        return False, None
    slot = int(parts[4])
    m = db.match(match_id)
    if not m or m["status"] != "live" or m["phase"] != "play":
        return False, "Only while live and in play phase."
    state = engine.pending_of(m)
    state["zone"] = 0
    state["last_pass"] = None
    state["beaten"] = []
    state["set_piece"] = None
    state["duel"] = None
    db.update_match(match_id, holder=slot, phase="play", pending=json.dumps(state))
    from .core import render_match
    render_match(match_id)
    return True, f"➡️ Ball to slot {slot}."


@action("mview", "match")
def act_mview(call, match_id):
    from .core import open_view
    m = db.match(match_id)
    if not m:
        return False, "Match gone."
    if open_view(m, call.message.chat.id):
        return True, "👁 Published here."
    return False, "Can't post here."


@action("mresettle", "match")
def act_mresettle(call, match_id):
    m = db.match(match_id)
    if not m or m["status"] != "done":
        return False, "Match isn't done."
    report, level_ups = payouts.settle_forced(match_id)
    safe(bot.send_message, call.message.chat.id, report)
    return True, "🏆 Re-settled (check payouts above)."


# ------------------------------------------------------------------ match control hub

@reg("mctl")
def mctl_panel(ctx: int, page: int):
    live = db.matches_page(0, PAGE, ("open", "live"))
    text = (
        "🎮 <b>MATCH CONTROL</b>\n" + RULE + "\n"
        "<i>Quick control over all active matches.</i>"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    for m in live:
        label = f"{'🟢' if m['status'] == 'live' else '🕓'} #{m['id']} {m['score1']}-{m['score2']} · {MODES.get(m['mode'], m['mode'])} {m['size']}v{m['size']}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"adm|match|{m['id']}|0"))
    if not live:
        text += "\n<i>— no active matches —</i>"
    kb.add(types.InlineKeyboardButton("🏁 Force-finish by ID: /afinish ID", callback_data="adm|noop|0|0"))
    kb.add(types.InlineKeyboardButton("⚔️ All matches", callback_data="adm|matches|0|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@bot.message_handler(commands=["afinish"])
@admin_guard
def afinish_cmd(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        safe(bot.reply_to, message, "Usage: <code>/afinish 12</code>")
        return
    match_id = int(parts[1].lstrip("#"))
    m = db.match(match_id)
    if not m or m["status"] != "live":
        safe(bot.reply_to, message, "No live match with that ID.")
        return
    from .handlers_match import finish
    finish(match_id)
    safe(bot.reply_to, message, f"🏁 Match #{match_id} settled and closed.")


@bot.message_handler(commands=["acancel"])
@admin_guard
def acancel_cmd(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        safe(bot.reply_to, message, "Usage: <code>/acancel 12</code>")
        return
    match_id = int(parts[1].lstrip("#"))
    m = db.match(match_id)
    if not m or m["status"] not in ("open", "live"):
        safe(bot.reply_to, message, "No active match with that ID.")
        return
    db.update_match(match_id, status="cancelled", phase="done", ended_at=db.now())
    from .core import edit_view
    edit_view(db.match(match_id), "🛑 <b>MATCH CANCELLED</b> (admin)", None)
    safe(bot.reply_to, message, f"🛑 Match #{match_id} cancelled — no payouts.")


# ------------------------------------------------------------------ wallet tools

@reg("wallet")
def wallet_panel(ctx: int, page: int):
    top = db.q("SELECT user_id, username, display, yen FROM players ORDER BY yen DESC LIMIT 10")
    row = db.stat_summary()
    lines = [
        f"{i + 1}. <b>{esc(r['display'] or r['username'] or f'ID{r['user_id']}')}</b> — {yen_short(r['yen'])}"
        for i, r in enumerate(top)
    ]
    mints = db.q(
        "SELECT COALESCE(SUM(amount),0) AS n FROM wallet_tx WHERE amount > 0"
    )[0]["n"]
    burns = db.q(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM wallet_tx WHERE amount < 0"
    )[0]["n"]
    text = (
        f"💰 <b>WALLET OVERVIEW</b>\n{RULE}\n"
        f"Circulating: <b>{yen_short(row['yen'])}</b> · players: {row['players']}\n"
        f"Σ minted: {yen_short(mints)} · Σ spent: {yen_short(burns)}\n"
        + RULE + "\n<b>TOP 10 RICHEST</b>\n" + "\n".join(lines or ["<i>— empty —</i>"])
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Grant everyone", callback_data="adm|wmass|0|0"),
        types.InlineKeyboardButton("👤 Per-player", callback_data="adm|players|0|0"),
    )
    kb.add(types.InlineKeyboardButton("✏️ /ayen @user ±amount", callback_data="adm|noop|0|0"))
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@bot.message_handler(commands=["ayen"])
@admin_guard
def ayen_cmd(message):
    parts = message.text.split()
    if len(parts) < 3 or not re.fullmatch(r"[+-]?\d{1,12}", parts[2]):
        safe(bot.reply_to, message, "Usage: <code>/ayen @user +500000</code>")
        return
    target = db.find_player(parts[1])
    delta = int(parts[2])
    if target:
        total = db.add_yen(target["user_id"], delta, f"admin @{message.from_user.username}")
        name = esc(target["display"] or target["username"])
        safe(bot.reply_to, message, f"💰 <b>{name}</b> → <b>{total:,}¥</b>")
    else:
        uname = parts[1].strip().lstrip("@").lower()
        total = db.add_pending_yen(uname, delta)
        safe(bot.reply_to, message, f"💰 <b>{total:,}¥</b> pending for <b>@{esc(uname)}</b>")


def _level_to_xp(level: int) -> int:
    level = max(1, min(MAX_LEVEL, level))
    return xp_for_level(level)


@bot.message_handler(commands=["alvl", "alevel"])
@admin_guard
def alvl_cmd(message):
    """Shift a player's level by a delta: /alvl @user +3 or /alvl @user -1."""
    parts = message.text.split()
    if len(parts) < 3 or not re.fullmatch(r"[+-]?\d{1,3}", parts[2]):
        safe(bot.reply_to, message, "Usage: <code>/alvl @user +3</code> or <code>/alvl @user -1</code>")
        return
    target = db.find_player(parts[1])
    if not target:
        safe(bot.reply_to, message, "Unknown player.")
        return
    delta = int(parts[2])
    cur = level_for(target["xp"])
    new = max(1, min(MAX_LEVEL, cur + delta))
    if new == cur:
        safe(bot.reply_to, message, f"No change — <b>{esc(target['display'] or target['username'])}</b> stays Lv {cur}.")
        return
    db.set_xp(target["user_id"], _level_to_xp(new))
    safe(
        bot.reply_to,
        message,
        f"📈 <b>{esc(target['display'] or target['username'])}</b> level {cur} → <b>{new}</b>",
    )


@bot.message_handler(commands=["asetlvl", "asetlevel"])
@admin_guard
def asetlvl_cmd(message):
    """Set a player's exact level: /asetlvl @user 20."""
    parts = message.text.split()
    if len(parts) < 3 or not re.fullmatch(r"\d{1,3}", parts[2]):
        safe(bot.reply_to, message, "Usage: <code>/asetlvl @user 20</code> (1–60)")
        return
    target = db.find_player(parts[1])
    if not target:
        safe(bot.reply_to, message, "Unknown player.")
        return
    cur = level_for(target["xp"])
    new = max(1, min(MAX_LEVEL, int(parts[2])))
    db.set_xp(target["user_id"], _level_to_xp(new))
    safe(
        bot.reply_to,
        message,
        f"📈 <b>{esc(target['display'] or target['username'])}</b> level {cur} → <b>{new}</b>",
    )


@action("wmass", "wallet")
def act_wmass(call, ctx):
    return False, "Use /awetall amount"


@bot.message_handler(commands=["awetall", "amass"])
@admin_guard
def awetall_cmd(message):
    parts = message.text.split()
    if len(parts) < 2 or not re.fullmatch(r"[+-]?\d{1,12}", parts[1]):
        safe(bot.reply_to, message, "Usage: <code>/awetall 100000</code> — pays every registered player.")
        return
    delta = int(parts[1])
    rows = db.q("SELECT user_id FROM players")
    for r in rows:
        db.add_yen(r["user_id"], delta, "admin mass payout")
    safe(bot.reply_to, message, f"💰 Paid {yen_short(delta)} to {len(rows)} player(s).")


# ------------------------------------------------------------------ characters

@reg("chars")
def chars_panel(ctx: int, page: int):
    taken = db.taken_keys()
    free_n = len(ROSTER) - len(taken)
    owners = {r["char_key"]: r["user_id"] for r in db.q("SELECT char_key, user_id FROM owned")}
    players = {r["user_id"]: r for r in db.q("SELECT user_id, username, display FROM players")}

    def owner_label(uid):
        p = players.get(uid)
        if not p:
            return f"ID{uid}"
        return p["display"] or p["username"] or f"ID{uid}"

    lines = [
        f"{'🔒' if k in taken else '🆓'} {icon_of(k)}{name_of(k)} · <i>{role_of(k)}</i>"
        + (f" → <b>{esc(owner_label(owners[k]))}</b>" if k in owners else "")
        for k in ROSTER
    ]
    text = (
        f"🃏 <b>CHARACTERS</b> — {free_n} free / {len(ROSTER)}\n{RULE}\n"
        + "\n".join(lines)
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("♻️ Reassign: /agive ID char", callback_data="adm|noop|0|0"),
        types.InlineKeyboardButton("👤 Players", callback_data="adm|players|0|0"),
    )
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@bot.message_handler(commands=["agive"])
@admin_guard
def agive_cmd(message):
    parts = message.text.split()
    if len(parts) < 3:
        safe(bot.reply_to, message, "Usage: <code>/agive @user rin</code>")
        return
    target = db.find_player(parts[1])
    if not target:
        safe(bot.reply_to, message, "Unknown player.")
        return
    key = resolve(parts[2])
    if key is None:
        safe(bot.reply_to, message, "Unknown character.")
        return
    taken = db.taken_keys()
    own = db.owned_by(target["user_id"])
    if own:
        taken.discard(own["char_key"])
    if key in taken:
        safe(bot.reply_to, message, f"❔ {name_of(key)} is already owned by someone else.")
        return
    db.force_assign_char(target["user_id"], key)
    safe(bot.reply_to, message, f"🃏 <b>{esc(target['display'] or target['username'])}</b> → {icon_of(key)}<b>{name_of(key)}</b>")


# ------------------------------------------------------------------ abilities

@reg("abilities")
def abilities_panel(ctx: int, page: int):
    from .config import ABILITIES_ENABLED
    text = (
        "⚡ <b>ABILITIES</b>\n" + RULE + "\n"
        f"Engine: <b>{'ON' if ABILITIES_ENABLED else 'OFF'}</b> · registry: {len(abilities.REGISTRY)} abilities\n"
        + "<i>Toggle via .env: BLUELOCK_ABILITIES=0/1 (restart needed)</i>"
        + "\n" + RULE + "\n<b>CATEGORIES</b>\n"
    )
    for cat, n in abilities.catalog_stats():
        icon = abilities.CATEGORY_ICON.get(cat, "·")
        text += f"{icon} {cat}: {n}\n"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 Sync catalog", callback_data="adm|catsync|0|0"),
        types.InlineKeyboardButton("🃏 Characters", callback_data="adm|chars|0|0"),
    )
    kb.add(
        types.InlineKeyboardButton("👤 Per-player unlocks", callback_data="adm|players|0|0"),
        types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"),
    )
    return text, kb


@action("catsync", "abilities")
def act_catsync(call, ctx):
    n = abilities.sync_catalog()
    return True, f"🔄 Catalog synced — {n} abilities."


# ------------------------------------------------------------------ broadcast

@reg("broadcast")
def broadcast_panel(ctx: int, page: int):
    n = db.count_players()
    text = (
        "📢 <b>BROADCAST</b>\n" + RULE + "\n"
        f"Targets: <b>{n}</b> registered players (PM).\n"
        "Send with: <code>/asay Your message here</code>\n"
        "<i>HTML formatting works. Use sparingly.</i>"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@bot.message_handler(commands=["asay"], func=lambda m: is_admin(m))
def asay_cmd(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe(bot.reply_to, message, "Usage: <code>/asay text</code>")
        return
    body = parts[1].strip()
    rows = db.q("SELECT user_id FROM players")
    ok = fail = 0
    for r in rows:
        sent = safe(bot.send_message, r["user_id"], f"📢 <b>BLUE LOCK</b>\n{RULE}\n{esc(body) if '<' not in body else body}")
        if sent is not None:
            ok += 1
        else:
            fail += 1
    safe(bot.reply_to, message, f"📢 Delivered: <b>{ok}</b> · failed: {fail}")


# ------------------------------------------------------------------ config / engine

@reg("config")
def config_panel(ctx: int, page: int):
    from . import config as cfg
    state = db.q1("SELECT COUNT(*) AS n FROM matches WHERE status IN ('open','live')")["n"]
    text = (
        "⚙️ <b>ENGINE / CONFIG</b>\n" + RULE + "\n"
        f"Season <b>{cfg.SEASON}</b> · race to <b>{cfg.GOAL_TARGET}</b>\n"
        f"Dice d{cfg.DICE_FACES} · keeper PWR {cfg.KEEPER_POWER} (catch {cfg.KEEPER_CATCH_ROLL}+)\n"
        f"Yen: goal {yen_short(cfg.GOAL_VALUE)} · assist {yen_short(cfg.ASSIST_VALUE)} · win {yen_short(cfg.WIN_VALUE)}\n"
        f"XP/level {cfg.XP_PER_LEVEL} · abilities {'on' if cfg.ABILITIES_ENABLED else 'off'}\n"
        f"Lobby TTL {cfg.LOBBY_TTL_HOURS}h · sweep every {cfg.LOBBY_SWEEP_SECONDS // 60}min\n"
        f"Active matches: <b>{state}</b>\n"
        + RULE + "\n"
        "<i>Values live in .env / config.py — restart to apply.</i>"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧹 Sweep stale lobbies", callback_data="adm|csweep|0|0"),
        types.InlineKeyboardButton("📊 DB stats", callback_data="adm|cstats|0|0"),
    )
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb


@action("csweep", "config")
def act_csweep(call, ctx):
    from main import sweep_lobbies
    n = sweep_lobbies()
    return True, f"🧹 Swept {n} stale lobby/lobbies."


@reg("cstats")
def cstats_panel(ctx: int, page: int):
    s = db.stat_summary()
    tables = db.q(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    counts = []
    for t in tables:
        n = db.q1(f"SELECT COUNT(*) AS n FROM {t['name']}")["n"]
        counts.append(f"• {t['name']}: {n}")
    text = (
        "📊 <b>DATABASE</b>\n" + RULE + "\n"
        f"Players {s['players']} · chars {s['chars']} · unlocks {s['unlocks']}\n"
        f"Matches {s['matches_total']} · wallet Σ{yen_short(s['tx_sum'])}\n"
        + RULE + "\n" + "\n".join(counts)
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩︎ Hub", callback_data="adm|hub|0|0"))
    return text, kb

