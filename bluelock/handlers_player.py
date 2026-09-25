import json
import re

from telebot import types

from . import abilities, db, economy, views
from .characters import (
    ROSTER,
    chibi_path,
    effective_stats,
    epithet_of,
    gacha,
    icon_of,
    name_of,
    overall,
    resolve,
    role_of,
)
from .config import (
    BOOST_LEVELS,
    MAX_BOOST,
    MAX_STAT,
    MAX_TITLE_LEN,
    REROLL_COST,
    STAT_ABBR,
    STAT_NAME,
    STATS,
    TITLE_COST,
    boosts_allowed,
    level_for,
    train_cost,
)
from .core import NO_CHAR, bot, safe, seen
from .fmt import RULE, bar, esc, mono, yen

NAME_OK = re.compile(r"^[a-zA-Z0-9_ ]{2,20}$")


def deliver_card(chat_id: int, text: str, char_key: str | None, reply_to_id: int | None = None):
    path = chibi_path(char_key) if char_key else None
    if path:
        with path.open("rb") as fh:
            safe(bot.send_photo, chat_id, fh, caption=text, reply_to_message_id=reply_to_id)
    else:
        safe(bot.send_message, chat_id, text, reply_to_message_id=reply_to_id)


def limit_rows(stats: dict[str, int]) -> list[str]:
    return [f"{STAT_ABBR[s]}  {stats[s]:>2}  {bar(stats[s], MAX_STAT, 8)}" for s in STATS]

HDR_START = (
    "⚽ <b>BLUE LOCK</b>\n"
    "<i>Every roll is a chance. Every match is a war.</i>\n"
    + RULE
)
HDR_SHOP = "🛒 <b>SHOP</b>"
HDR_CHARS = "📋 <b>CHARACTERS</b>\n<i>SHO·PAS·DRI·MET·FRK</i>"


@bot.message_handler(commands=["start", "help"])
def start(message):
    seen(message)
    row = db.player(message.from_user.id)
    own = db.owned_by(message.from_user.id)
    level = level_for(row["xp"])
    safe(
        bot.reply_to,
        message,
        HDR_START
        + "\n🎰 /gacha — Pull a character (first is free)\n"
        "🎴 /profile — Your stats and card\n"
        "🆔 /register name — Set your display name\n"
        "⚔️ /newmatch — Open a lobby (works right here in PM)\n"
        "📋 /matches — Find a match and join from any chat\n"
        "⚡ /abilities — Skills & passives; unlock deeper layers\n"
        "💪 /shop — Train stats, buy titles\n"
        "🏆 /top — Leaderboards\n"
        "📖 /rules — Duels, set pieces & penalty nerve\n"
        "💰 /balance — Wallet\n"
        "📅 /daily — Daily yen with a streak\n"
        "🎯 /quests — Daily quests for extra yen\n"
        "🏅 /medals — Your achievements\n"
        "📋 /chars — Character list\n"
        "🧤 /keeper — The goalkeeper's limits\n"
        "🏳️ /surrender — Your captain forfeits\n"
        + RULE
        + "<i>\n🛡 Passives are manual now — arm them from the button bar, 2 charges each."
        " ⚡ Skills fire once per match. 🎲 Gamble skills roll your die and let fate decide.</i>\n"
        + f"💰 <b>{yen(row['yen'])}</b> · Lv <b>{level}</b>"
        + ("" if own else "\n\n<i>No character yet — /gacha to pull one.</i>"),
    )


@bot.message_handler(commands=["rules"])
def rules_cmd(message):
    seen(message)
    safe(bot.reply_to, message, views.rules_text())


@bot.message_handler(commands=["register"])
def register(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe(bot.reply_to, message, "Usage: <code>/register YourName</code>")
        return

    name = " ".join(parts[1].split())
    if not NAME_OK.match(name):
        safe(bot.reply_to, message, "Name must be 2-20 characters, letters and numbers only.")
        return
    if not db.set_display(message.from_user.id, name):
        safe(bot.reply_to, message, "That name is taken. Try another.")
        return
    safe(bot.reply_to, message, f"✅ You're now known as <b>{esc(name)}</b>.")


def _pull(message, paid: bool):
    user_id = message.from_user.id
    current = db.owned_by(user_id)

    if current and not paid:
        safe(
            bot.reply_to,
            message,
            f"You already have <b>{esc(name_of(current['char_key']))}</b>.\n"
            f"To re-roll: /reroll — <b>{yen(REROLL_COST)}</b>\n"
            "<i>Your training boosts will be lost. Unlocked abilities stay banked for that character.</i>",
        )
        return

    taken = db.taken_keys()
    if current:
        taken.discard(current["char_key"])
    char_key = gacha(taken)
    if char_key is None:
        safe(bot.reply_to, message, "All characters are taken. Nothing left to pull.")
        return

    if paid and not db.spend_yen(user_id, REROLL_COST, "character reroll"):
        row = db.player(user_id)
        safe(bot.reply_to, message, f"Not enough yen. Need {yen(REROLL_COST)} — you have {yen(row['yen'])}")
        return

    db.assign_char(user_id, char_key)
    stats = effective_stats(char_key, {})
    key = current["char_key"] if current else None
    released = f"\n♻️ <b>{esc(name_of(key))}</b> released." if key else ""
    kit_hint = (
        f"\n⚡ Kit unlocked: {' · '.join(ab.name for ab in abilities.kit_for_char(char_key) if ab.tier == 1)}"
        if abilities.enabled()
        else ""
    )

    deliver_card(
        message.chat.id,
        f"🎰 <b>{icon_of(char_key)} {esc(name_of(char_key))}</b>\n"
        f"<i>«{esc(epithet_of(char_key))}» · {esc(role_of(char_key))}</i>\n"
        + mono([f"OVR {overall(stats)}", ""] + limit_rows(stats))
        + kit_hint
        + released,
        char_key,
        message.message_id,
    )


@bot.message_handler(commands=["gacha"])
def gacha_cmd(message):
    seen(message)
    _pull(message, paid=False)


@bot.message_handler(commands=["reroll"])
def reroll_cmd(message):
    seen(message)
    if not db.owned_by(message.from_user.id):
        _pull(message, paid=False)
        return
    _pull(message, paid=True)


@bot.message_handler(commands=["profile", "me"])
def profile(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    target = db.find_player(parts[1]) if len(parts) > 1 else db.player(message.from_user.id)
    if not target:
        safe(bot.reply_to, message, "I don't know that player.")
        return
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🃏 Quick Card", callback_data=f"card|{target['user_id']}"),
        types.InlineKeyboardButton("⚡ My Kit", callback_data="openkit"),
    )
    if target["user_id"] == message.from_user.id:
        kb.add(
            types.InlineKeyboardButton("💪 Shop / Train", callback_data="shopopen"),
            types.InlineKeyboardButton("💰 History", callback_data="mytx"),
        )
    safe(bot.reply_to, message, views.profile_text(target), reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "shopopen")
def shopopen_cb(call):
    seen(call)
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(bot.send_message, call.message.chat.id, shop_body(call.from_user.id), reply_markup=shop_markup(call.from_user.id))


@bot.callback_query_handler(func=lambda c: c.data == "mytx")
def mytx_cb(call):
    seen(call)
    txs = db.q("SELECT amount, reason FROM wallet_tx WHERE user_id=? ORDER BY id DESC LIMIT 5", (call.from_user.id,))
    rows = "\n".join(
        f" {'🟢' if t['amount'] > 0 else '🔴'} {t['amount']:+,} — <i>{esc(t['reason'])}</i>" for t in txs
    ) or " <i>No transactions yet.</i>"
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(bot.send_message, call.message.chat.id, f"💰 <b>HISTORY</b>\n{RULE}\n{rows}")


@bot.message_handler(commands=["card"])
def card(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    target = db.find_player(parts[1]) if len(parts) > 1 else db.player(message.from_user.id)
    if not target:
        safe(bot.reply_to, message, "I don't know that player.")
        return
    own = db.owned_by(target["user_id"])
    deliver_card(
        message.chat.id,
        views.card_text(target),
        own["char_key"] if own else None,
        message.message_id,
    )


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("card|"))
def card_cb(call):
    seen(call)
    if not call.message:
        safe(bot.answer_callback_query, call.id)
        return
    try:
        target = db.player(int(call.data.split("|")[1]))
    except ValueError:
        target = None
    if target:
        safe(bot.answer_callback_query, call.id)
        own = db.owned_by(target["user_id"])
        deliver_card(
            call.message.chat.id,
            views.card_text(target),
            own["char_key"] if own else None,
        )


@bot.message_handler(commands=["balance", "wallet"])
def balance(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        target = db.find_player(parts[1])
        if target:
            safe(bot.reply_to, message, f"💰 <b>{esc(target['display'] or target['username'])}</b> balance: <b>{yen(target['yen'])}</b>")
        else:
            pend = db.q1("SELECT amount FROM pending_yen WHERE username=?", (parts[1].strip().lstrip('@').lower(),))
            amount = pend["amount"] if pend else 0
            safe(bot.reply_to, message, f"💰 <b>{yen(amount)}</b> <i>(pending — hasn't messaged the bot yet)</i>")
        return

    row = db.player(message.from_user.id)
    txs = db.q("SELECT amount, reason FROM wallet_tx WHERE user_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id,))
    history = "\n".join(
        f" {'🟢' if t['amount'] > 0 else '🔴'} {t['amount']:+,} — <i>{esc(t['reason'])}</i>" for t in txs
    ) or " <i>No transactions yet.</i>"
    safe(bot.reply_to, message, f"💰 <b>BALANCE</b>\n{RULE}\n<b>{yen(row['yen'])}</b>\n{RULE}\n{history}")


# ------------------------------------------------------------------ daily & quests

HDR_DAILY = "📅 <b>DAILY</b>"
HDR_QUESTS = "🎯 <b>DAILY QUESTS</b>"


@bot.message_handler(commands=["daily"])
def daily_cmd(message):
    seen(message)
    user_id = message.from_user.id
    day = economy.local_day()
    amount, streak = economy.claim(user_id, day)
    if amount is None:
        row = db.daily_row(user_id)
        streak = row["streak"] if row else 0
        next_amt = economy.daily_amount(min(economy.DAILY_MAX_STREAK, streak + 1))
        safe(
            bot.reply_to,
            message,
            f"{HDR_DAILY}\n{RULE}\n"
            f"✅ Already claimed today — streak <b>{streak}/{economy.DAILY_MAX_STREAK}</b> 🔥\n"
            f"⏳ Come back tomorrow: <b>{yen(next_amt)}</b>\n{RULE}\n"
            + economy.quests_summary(user_id, day),
        )
        return
    safe(
        bot.reply_to,
        message,
        f"{HDR_DAILY}\n{RULE}\n"
        f"🔥 Streak <b>{streak}/{economy.DAILY_MAX_STREAK}</b>\n"
        f"💰 Claimed <b>{yen(amount)}</b>\n{RULE}\n"
        "<i>Keep coming back — the streak grows to "
        f"{yen(economy.daily_amount(economy.DAILY_MAX_STREAK))}.</i>\n"
        + economy.quests_summary(user_id, day),
        reply_markup=quests_keyboard(user_id, day),
    )


def quests_keyboard(user_id: int, day: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    claimed = set(economy.quest_state(user_id, day)["claimed"])
    stats = economy.today_stats(user_id, day)
    for qid in economy.pick_quests(day):
        if qid in claimed:
            continue
        if economy.quest_progress(qid, stats) >= economy.quest_target(qid):
            kb.add(types.InlineKeyboardButton(
                f"🎁 Claim {economy.QUEST_EMOJI[qid]} {economy.quest_def(qid)[1]}",
                callback_data=f"qclaim|{qid}",
            ))
    if kb.keyboard:
        kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="qrefresh"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("qclaim|"))
def qclaim_cb(call):
    seen(call)
    qid = call.data.split("|")[1]
    day = economy.local_day()
    amount = economy.claim_quest(call.from_user.id, qid, day)
    if amount is None:
        safe(bot.answer_callback_query, call.id, "Not claimable yet — finish the quest first.", show_alert=True)
        return
    safe(bot.answer_callback_query, call.id, f"✅ +{yen(amount)}")
    if call.message:
        row = db.player(call.from_user.id)
        safe(
            bot.edit_message_text,
            f"{HDR_QUESTS}\n{RULE}\n" + economy.quests_summary(call.from_user.id, day) + f"\n💰 Balance: <b>{yen(row['yen'])}</b>",
            call.message.chat.id,
            call.message.message_id,
        )


@bot.callback_query_handler(func=lambda c: c.data == "qrefresh")
def qrefresh_cb(call):
    seen(call)
    day = economy.local_day()
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(
            bot.edit_message_text,
            f"{HDR_QUESTS}\n{RULE}\n" + economy.quests_summary(call.from_user.id, day),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=quests_keyboard(call.from_user.id, day),
        )


@bot.message_handler(commands=["quests"])
def quests_cmd(message):
    seen(message)
    day = economy.local_day()
    safe(
        bot.reply_to,
        message,
        f"{HDR_QUESTS}\n{RULE}\n" + economy.quests_summary(message.from_user.id, day)
        + f"\n🎁 Each finished quest pays <b>{yen(economy.QUEST_REWARD)}</b>.",
        reply_markup=quests_keyboard(message.from_user.id, day),
    )


@bot.message_handler(commands=["medals", "achievements"])
def medals_cmd(message):
    seen(message)
    rows = db.achievements_of(message.from_user.id)
    owned = {r["medal"] for r in rows}
    lines = []
    for key, label in economy.MEDALS:
        mark = label if key in owned else f"▫️ {label.split(' ', 1)[1]} — locked"
        lines.append(mark)
    safe(
        bot.reply_to,
        message,
        f"🏅 <b>MEDALS</b>\n{RULE}\n" + "\n".join(lines) + f"\n{RULE}\n<i>{len(owned)}/{len(economy.MEDALS)} earned.</i>",
    )


@bot.message_handler(commands=["top", "leaderboard"])
def top(message):
    seen(message)
    safe(bot.reply_to, message, views.leaderboard_text("goals"), reply_markup=views.leaderboard_keyboard("goals"))


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("lb|"))
def lb_cb(call):
    seen(call)
    field = call.data.split("|")[1]
    if field not in views.LB_TITLES:
        safe(bot.answer_callback_query, call.id)
        return
    if not call.message:
        safe(bot.answer_callback_query, call.id)
        return
    safe(
        bot.edit_message_text,
        views.leaderboard_text(field),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=views.leaderboard_keyboard(field),
    )
    safe(bot.answer_callback_query, call.id)


# ------------------------------------------------------------------ abilities

@bot.message_handler(commands=["abilities", "skills", "kit"])
def abilities_cmd(message):
    seen(message)
    own = db.owned_by(message.from_user.id)
    if not own:
        safe(bot.reply_to, message, NO_CHAR)
        return
    text, kb = views.kit_page(message.from_user.id, own["char_key"])
    safe(bot.reply_to, message, text, reply_markup=kb)


def _edit_kit_page(call, user_id, char_key):
    text, kb = views.kit_page(user_id, char_key)
    safe(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("unlock|"))
def unlock_cb(call):
    seen(call)
    aid = call.data.split("|", 1)[1]
    ab = abilities.get(aid)
    if ab is None or ab.tier == 1:
        safe(bot.answer_callback_query, call.id)
        return
    own = db.owned_by(call.from_user.id)
    if not own or own["char_key"] != ab.char:
        safe(bot.answer_callback_query, call.id, "That ability belongs to another character.", show_alert=True)
        return
    cost, need_lv = abilities.price_and_level(ab)
    level = level_for(db.player(call.from_user.id)["xp"])
    if level < need_lv:
        safe(bot.answer_callback_query, call.id, f"🔒 Requires level {need_lv}. You are Lv {level}.", show_alert=True)
        return
    if not db.buy_unlock(call.from_user.id, aid, cost, f"unlock {ab.name}"):
        safe(bot.answer_callback_query, call.id, f"Not enough yen — need {cost:,}¥.", show_alert=True)
        return
    safe(bot.answer_callback_query, call.id, f"✅ {ab.name} unlocked!")
    if call.message:
        _edit_kit_page(call, call.from_user.id, own["char_key"])


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("kitrefresh|"))
def kitrefresh_cb(call):
    seen(call)
    own = db.owned_by(call.from_user.id)
    if not own or not call.message:
        safe(bot.answer_callback_query, call.id)
        return
    _edit_kit_page(call, call.from_user.id, own["char_key"])
    safe(bot.answer_callback_query, call.id)


# ------------------------------------------------------------------ shop

def next_boost_level(spent: int) -> int:
    return BOOST_LEVELS[min(spent, len(BOOST_LEVELS) - 1)]


TITLE_PRESETS = ("The Monster", "Ace Striker", "Blue Lock MVP", "Chosen One", "Devourer")


def shop_markup(user_id: int) -> types.InlineKeyboardMarkup:
    own = db.owned_by(user_id)
    row = db.player(user_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    if own:
        boosts = json.loads(own["boosts"])
        spent = sum(min(MAX_BOOST, boosts.get(s, 0)) for s in STATS)
        allowed = boosts_allowed(level_for(row["xp"]))
        if spent >= len(BOOST_LEVELS):
            kb.add(types.InlineKeyboardButton("💪 All training slots used ✅", callback_data="noop"))
        else:
            for s in STATS:
                level = min(MAX_BOOST, boosts.get(s, 0))
                if level >= MAX_BOOST:
                    kb.add(types.InlineKeyboardButton(f"{STAT_NAME[s]} — MAX ✅", callback_data="noop"))
                elif spent >= allowed:
                    kb.add(types.InlineKeyboardButton(
                        f"🔒 {STAT_NAME[s]} — needs Lv {next_boost_level(spent)}", callback_data="noop"
                    ))
                else:
                    kb.add(types.InlineKeyboardButton(
                        f"💪 Train {STAT_NAME[s]} (+1) — {train_cost(level):,}¥",
                        callback_data=f"train|{s}",
                    ))
        if abilities.enabled():
            locked = [
                ab for ab in abilities.kit_for_char(own["char_key"])
                if ab.tier > 1 and ab.id not in db.unlocked_ids(user_id)
            ]
            label = f"⚡ Abilities — {len(locked)} unlock(s) available" if locked else "⚡ Abilities — view kit"
            kb.add(types.InlineKeyboardButton(label, callback_data="openkit"))
    kb.add(types.InlineKeyboardButton(f"🎰 Reroll character — {REROLL_COST:,}¥", callback_data="buyroll"))
    kb.add(types.InlineKeyboardButton(f"🏷 Pick a title — {TITLE_COST:,}¥", callback_data="titles"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "titles")
def titles_cb(call):
    seen(call)
    safe(bot.answer_callback_query, call.id)
    if not call.message:
        return
    row = db.player(call.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for t in TITLE_PRESETS:
        kb.add(types.InlineKeyboardButton(
            f"🏷 {t}", callback_data=f"settitle|{t}"
        ))
    kb.add(types.InlineKeyboardButton(
        "✏️ Custom: /title YourTitle", callback_data="noop"
    ))
    kb.add(types.InlineKeyboardButton("↩︎ Back", callback_data="shopback"))
    safe(
        bot.edit_message_text,
        f"{HDR_SHOP}\n💰 <b>{yen(row['yen'])}</b>\n{RULE}\nPick a title — cost <b>{yen(TITLE_COST)}</b>:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data == "shopback")
def shopback_cb(call):
    seen(call)
    safe(bot.answer_callback_query, call.id)
    if call.message:
        safe(
            bot.edit_message_text,
            shop_body(call.from_user.id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=shop_markup(call.from_user.id),
        )


def shop_body(user_id: int) -> str:
    row = db.player(user_id)
    own = db.owned_by(user_id)
    body = f"{HDR_SHOP}\n💰 <b>{yen(row['yen'])}</b>\n"
    if own:
        boosts = json.loads(own["boosts"])
        spent = sum(min(MAX_BOOST, boosts.get(s, 0)) for s in STATS)
        allowed = boosts_allowed(level_for(row["xp"]))
        eff = effective_stats(own["char_key"], boosts)
        level = level_for(row["xp"])
        body += (
            f"{RULE}\n"
            f"{icon_of(own['char_key'])}<b>{esc(name_of(own['char_key']))}</b> · <b>{overall(eff)} OVR</b>\n"
            f"💪 Slots <b>{spent}/{allowed}</b>"
        )
        if spent >= allowed:
            nxt = next((lv for lv in BOOST_LEVELS if lv > level), None)
            if nxt:
                body += f" — 🔒 next slot at Lv {nxt}"
        body += "\n<i>Each +1 costs a slot & yen.\nAbilities live in /abilities.</i>"
    else:
        body += f"{RULE}\n{NO_CHAR}"
    return body


@bot.message_handler(commands=["shop"])
def shop(message):
    seen(message)
    safe(bot.reply_to, message, shop_body(message.from_user.id), reply_markup=shop_markup(message.from_user.id))


@bot.callback_query_handler(func=lambda c: c.data == "openkit")
def openkit_cb(call):
    seen(call)
    own = db.owned_by(call.from_user.id)
    if not own or not call.message:
        safe(bot.answer_callback_query, call.id)
        return
    text, kb = views.kit_page(call.from_user.id, own["char_key"])
    safe(bot.edit_message_text, text, call.message.chat.id, call.message.message_id, reply_markup=kb)
    safe(bot.answer_callback_query, call.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("train|"))
def train_cb(call):
    seen(call)
    stat = call.data.split("|")[1]
    if stat not in STATS:
        safe(bot.answer_callback_query, call.id)
        return
    own = db.owned_by(call.from_user.id)
    if not own:
        safe(bot.answer_callback_query, call.id, NO_CHAR, show_alert=True)
        return

    boosts = json.loads(own["boosts"])
    level = min(MAX_BOOST, boosts.get(stat, 0))
    if level >= MAX_BOOST:
        safe(bot.answer_callback_query, call.id, "This stat is maxed out.", show_alert=True)
        return

    row = db.player(call.from_user.id)
    spent = sum(min(MAX_BOOST, boosts.get(s, 0)) for s in STATS)
    if spent >= boosts_allowed(level_for(row["xp"])):
        safe(
            bot.answer_callback_query,
            call.id,
            f"🔒 Next upgrade slot unlocks at level {next_boost_level(spent)}.",
            show_alert=True,
        )
        return

    cost = train_cost(level)
    if not db.spend_yen(call.from_user.id, cost, f"train {STAT_NAME[stat]}"):
        safe(bot.answer_callback_query, call.id, f"Need {cost:,}¥", show_alert=True)
        return

    db.bump_boost(call.from_user.id, stat)
    safe(bot.answer_callback_query, call.id, f"✅ {STAT_NAME[stat]} +1!")
    row = db.player(call.from_user.id)
    if call.message:
        safe(
            bot.edit_message_text,
            shop_body(call.from_user.id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=shop_markup(call.from_user.id),
        )


@bot.callback_query_handler(func=lambda c: c.data == "buyroll")
def buyroll_cb(call):
    seen(call)
    user_id = call.from_user.id
    current = db.owned_by(user_id)
    if current and not db.spend_yen(user_id, REROLL_COST, "character reroll"):
        row = db.player(user_id)
        safe(
            bot.answer_callback_query,
            call.id,
            f"Not enough yen — need {yen(REROLL_COST)}, you have {yen(row['yen'])}.",
            show_alert=True,
        )
        return
    taken = db.taken_keys()
    if current:
        taken.discard(current["char_key"])
    char_key = gacha(taken)
    if char_key is None:
        if current:
            db.add_yen(user_id, REROLL_COST, "reroll refund — pool empty")
        safe(bot.answer_callback_query, call.id, "All characters are taken.", show_alert=True)
        return
    db.assign_char(user_id, char_key)
    safe(bot.answer_callback_query, call.id, f"✨ {name_of(char_key)}!")
    if call.message:
        stats = effective_stats(char_key, {})
        kit_hint = (
            f"\n⚡ Kit: {' · '.join(ab.name for ab in abilities.kit_for_char(char_key) if ab.tier == 1)}"
            if abilities.enabled()
            else ""
        )
        released = (
            f"\n♻️ <b>{esc(name_of(current['char_key']))}</b> released."
            if current
            else ""
        )
        deliver_card(
            call.message.chat.id,
            f"🎰 <b>{icon_of(char_key)}{esc(name_of(char_key))}</b>\n"
            f"<i>«{esc(epithet_of(char_key))}» · {esc(role_of(char_key))}</i>\n"
            + mono([f"OVR {overall(stats)}", ""] + limit_rows(stats))
            + kit_hint
            + released,
            char_key,
        )
        safe(
            bot.edit_message_text,
            shop_body(user_id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=shop_markup(user_id),
        )


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settitle|"))
def settitle_cb(call):
    seen(call)
    if not call.message:
        safe(bot.answer_callback_query, call.id)
        return
    text = call.data.split("|", 1)[1]
    if not NAME_OK.match(text.replace(" ", "a")):
        safe(bot.answer_callback_query, call.id, "Letters and numbers only.", show_alert=True)
        return
    if not db.spend_yen(call.from_user.id, TITLE_COST, "buy title"):
        safe(bot.answer_callback_query, call.id, f"Need {yen(TITLE_COST)}", show_alert=True)
        return
    db.set_title(call.from_user.id, text)
    safe(bot.answer_callback_query, call.id, f"🏷 {text}")
    safe(
        bot.edit_message_text,
        shop_body(call.from_user.id),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=shop_markup(call.from_user.id),
    )


@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_cb(call):
    safe(bot.answer_callback_query, call.id)


@bot.message_handler(commands=["title"])
def title_cmd(message):
    seen(message)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        safe(bot.reply_to, message, f"Usage: <code>/title YourTitle</code> — cost {yen(TITLE_COST)}")
        return
    text = " ".join(parts[1].split())[:MAX_TITLE_LEN]
    if not NAME_OK.match(text.replace(" ", "a")):
        safe(bot.reply_to, message, "Letters and numbers only.")
        return
    if not db.spend_yen(message.from_user.id, TITLE_COST, "buy title"):
        safe(bot.reply_to, message, f"Need {yen(TITLE_COST)}")
        return
    db.set_title(message.from_user.id, text)
    safe(bot.reply_to, message, f"🏷 Title set: <b>{esc(text)}</b>")


@bot.message_handler(commands=["chars", "roster"])
def chars(message):
    seen(message)
    taken = db.taken_keys()
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1:
        key = resolve(parts[1])
        if key is None:
            safe(bot.reply_to, message, "Character not found.")
            return
        stats = effective_stats(key, {})
        owner = "🔒 Taken" if key in taken else "🆓 Available"
        kit_line = ""
        if abilities.enabled():
            starters = [abilities.get(aid) for aid in abilities.starter_ids(key)]
            kit_line = "⚡ " + " · ".join(ab.name for ab in starters if ab) + "\n"
        safe(
            bot.reply_to,
            message,
            f"{icon_of(key)}<b>{esc(name_of(key))}</b> · <b>{overall(stats)} OVR</b>\n"
            f"<i>{esc(epithet_of(key))} · {esc(role_of(key))}</i> · {owner}\n"
            + "<pre>"
            + "\n".join(f"{STAT_ABBR[s]} {stats[s]:>2} {bar(stats[s], MAX_STAT)}" for s in STATS)
            + "</pre>\n"
            + kit_line,
        )
        return

    rows = [
        f"{'🔒' if key in taken else '🆓'} {icon_of(key).rstrip()} {name:<24} {'-'.join(str(v) for v in stats)}"
        for key, (name, rarity, stats, _) in ROSTER.items()
    ]
    free_n = len(ROSTER) - len(taken)
    safe(
        bot.reply_to,
        message,
        HDR_CHARS + "\n<pre>" + "\n".join(rows) + "</pre>"
        f"\n<i>🔒 = taken · 🆓 = free ({free_n} left)</i>\n"
        f"\n<i>Limits run 1–{MAX_STAT}; training adds up to +{MAX_BOOST}.</i>\n"
        f"\n<i>/chars name · limits 1–{MAX_STAT} (+{MAX_BOOST} training)</i>",
    )


@bot.message_handler(commands=["keeper", "gk"])
def keeper_cmd(message):
    seen(message)
    safe(bot.reply_to, message, views.keeper_card())
