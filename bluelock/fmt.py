import html
import re


def header(emoji: str, title: str, sub: str | None = None) -> str:
    """Canonical screen header: emoji + TITLE (+ italic sub) + rule.

    Every screen starts with this so the bot reads as one product.
    """
    head = f"{emoji} <b>{title}</b>"
    if sub:
        head += f"\n<i>{sub}</i>"
    return head + "\n" + RULE


def hint(text: str) -> str:
    return f"<i>{text}</i>"


RULE = "──────────────"
HEAVY = "━━━━━━━━━━━━"

_TAG = re.compile(r"<[^>]+>")


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def strip_tags(text: str) -> str:
    return _TAG.sub("", text)


def clip(text: str, width: int = 46) -> str:
    plain = " ".join(strip_tags(text).split())
    if len(plain) <= width:
        return plain
    return plain[: width - 1].rstrip() + "…"


def yen(amount: int) -> str:
    return f"¥{int(amount):,}"


def yen_short(amount: int) -> str:
    n = int(amount)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000:
        s = f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{sign}¥{s}M"
    if n >= 1_000:
        return f"{sign}¥{round(n / 1_000)}K"
    return f"{sign}¥{n}"


def bar(current: int | float, total: int | float, width: int = 8) -> str:
    if total <= 0:
        return "▱" * width
    done = max(0, min(width, round(width * current / total)))
    return "▰" * done + "▱" * (width - done)


def pips(done: int, total: int) -> str:
    done = max(0, min(done, total))
    return "●" * done + "○" * max(0, total - done)


def mono(rows: list[str]) -> str:
    return "<pre>" + "\n".join(rows) + "</pre>"


def quote(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"


def kv_line(pairs: list[tuple[str, str]], sep: str = " · ") -> str:
    return sep.join(f"{key} {value}" for key, value in pairs if value)


MEDALS = ("🥇", "🥈", "🥉")


def place(i: int) -> str:
    return MEDALS[i] if i < len(MEDALS) else f"{i + 1}."
