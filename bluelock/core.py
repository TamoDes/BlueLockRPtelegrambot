import logging

import telebot

from . import db, views
from .config import ADMINS, ADMIN_IDS, BOT_TOKEN, LEVEL_UP_BONUS, boosts_allowed, rank_for
from .fmt import esc, yen

logger = logging.getLogger("bluelock")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

NOT_ADMIN = "🚫 Admins only."
NO_CHAR = "❔ No character yet — /gacha to pull one."


def is_admin(event) -> bool:
    user = event.from_user
    if not user:
        return False
    if user.id in ADMIN_IDS:
        return True
    return bool(user.username and user.username.lower() in ADMINS)


def cb_int(event) -> int | None:
    try:
        return int(event.data.split("|")[1])
    except (IndexError, ValueError):
        return None


def seen(event) -> None:
    user = event.from_user
    if user and not user.is_bot:
        db.touch_player(user.id, user.username)


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            logger.info("telegram call skipped: %s", e)
    except Exception as e:
        logger.info("telegram call failed: %s", e)
    return None


def display_name(user) -> str:
    row = db.player(user.id)
    if row and row["display"]:
        return row["display"]
    return user.username or user.first_name or f"ID{user.id}"


def edit_view(match, text: str, markup) -> None:
    if match["message_id"]:
        safe(bot.edit_message_text, text, match["chat_id"], match["message_id"], reply_markup=markup)
    for row in db.views_of(match["id"]):
        if row["chat_id"] == match["chat_id"]:
            continue
        safe(bot.edit_message_text, text, row["chat_id"], row["message_id"], reply_markup=markup)


def is_pm(match) -> bool:
    return match["chat_id"] > 0


def open_view(match, chat_id: int) -> bool:
    """Open (or refresh) this match's live view in a chat. False if posting failed."""
    if chat_id == match["chat_id"]:
        return True
    roster = db.roster(match["id"])
    if match["status"] == "open":
        text, markup = views.lobby_text(match, roster), views.lobby_keyboard(match, roster)
    else:
        text, markup = views.scoreboard(match, roster), views.action_keyboard(match, roster)

    existing = next((r for r in db.views_of(match["id"]) if r["chat_id"] == chat_id), None)
    if existing is not None:
        edited = safe(
            bot.edit_message_text, text, chat_id, existing["message_id"], reply_markup=markup
        )
        if edited is not None:
            return True
        db.drop_view(match["id"], chat_id)

    sent = safe(bot.send_message, chat_id, text, reply_markup=markup)
    if sent is None:
        return False
    db.add_view(match["id"], chat_id, sent.message_id)
    return True


def broadcast(match, text: str, skip: int | None = None) -> None:
    targets = {match["chat_id"]} | {r["chat_id"] for r in db.views_of(match["id"])}
    targets.discard(skip)
    for chat_id in targets:
        safe(bot.send_message, chat_id, text)


def render_lobby(match_id: int) -> None:
    match = db.match(match_id)
    if not match:
        return
    roster = db.roster(match_id)
    edit_view(match, views.lobby_text(match, roster), views.lobby_keyboard(match, roster))


def render_match(match_id: int, keyboard=None) -> None:
    match = db.match(match_id)
    if not match:
        return
    roster = db.roster(match_id)
    markup = keyboard if keyboard is not None else views.action_keyboard(match, roster)
    edit_view(match, views.scoreboard(match, roster), markup)


def announce_levelups(chat_id: int, level_ups: list) -> None:
    for user_id, old, new in level_ups:
        row = db.player(user_id)
        rname, ricon = rank_for(new)
        name = esc(row["display"] or (f"@{row['username']}" if row["username"] else "Player"))
        text = (
            f"📈 <b>{name}</b> leveled up {old} → <b>{new}</b>!\n"
            f"{ricon} Rank: <b>{esc(rname)}</b>\n"
            f"💰 Bonus: <b>{yen(LEVEL_UP_BONUS * (new - old))}</b>"
        )
        if boosts_allowed(new) > boosts_allowed(old):
            text += "\n💪 New training slot unlocked — /shop"
        safe(bot.send_message, chat_id, text)
