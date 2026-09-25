from telebot import types

from . import db, views
from .characters import name_of
from .config import level_for
from .core import bot, safe, seen
from .fmt import esc, yen


def article(uid: str, title: str, text: str, description: str):
    return types.InlineQueryResultArticle(
        id=uid,
        title=title,
        description=description,
        input_message_content=types.InputTextMessageContent(text, parse_mode="HTML"),
    )


BAL_WORDS = ("balance", "wallet", "yen", "money")
CARD_WORDS = ("card", "profile", "me", "char")


@bot.inline_handler(lambda q: True)
def inline(query):
    seen(query)
    text = query.query.strip().lower()
    results = []

    me = db.player(query.from_user.id)
    if me:
        if not text or any(k in text for k in BAL_WORDS):
            results.append(
                article(
                    "my-balance",
                    f"💰 My balance — {yen(me['yen'])}",
                    f"💰 Balance of <b>{esc(me['display'] or me['username'] or 'me')}</b>: <b>{yen(me['yen'])}</b>",
                    "Send your balance",
                )
            )
        if not text or any(k in text for k in CARD_WORDS):
            results.append(article("my-card", "🎴 My card", views.card_text(me), "Your player card"))

    for field, (icon, title) in views.LB_TITLES.items():
        if not text or text in field or text in title.lower():
            results.append(
                article(f"lb-{field}", f"{icon} {title}", views.leaderboard_text(field), f"Board: {title}")
            )

    if text:
        for row in db.search_players(text):
            if row["user_id"] == query.from_user.id:
                continue
            name = row["display"] or (f"@{row['username']}" if row["username"] else f"ID{row['user_id']}")
            own = db.owned_by(row["user_id"])
            char = f" • {name_of(own['char_key'])}" if own else ""
            results.append(
                article(f"p-{row['user_id']}", f"🎴 {name}", views.card_text(row),
                        f"Lv {level_for(row['xp'])}{char}")
            )

    safe(bot.answer_inline_query, query.id, results[:45], cache_time=3, is_personal=True)
