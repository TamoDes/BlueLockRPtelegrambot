import random
from pathlib import Path

from .config import BASE_DIR, BASE_MAX, MAX_BOOST, MAX_STAT, RARITY_WEIGHT, STATS

CHIBI_DIR = BASE_DIR / "playerchibiicons"


def chibi_path(char_key: str) -> Path | None:
    p = CHIBI_DIR / f"{char_key}.png"
    return p if p.is_file() else None

# (name, rarity, (shot, passing, dribble, meta, freekick), title)
# skills/passives: filled per-character by abilities.py / abilities_extra.py
ROSTER = {
    # ── Nigeria ──────────────────────────────────────────────────────────────
    "kuso":       ("Godwin Kuso",       "SR",  (3, 6, 5, 5, 2), "Tempo Controller"),
    "umaru":      ("Umaru",             "N",   (5, 3, 3, 3, 2), "Forward"),

    # ── Master Strikers / World Five ────────────────────────────────────────
    "noa":        ("Noel Noa",          "SSR", (6, 5, 5, 5, 3), "The Strongest"),
    "prince":     ("Chris Prince",      "SSR", (6, 3, 3, 5, 5), "The Prince"),
    "snuffy":     ("Marc Snuffy",       "SSR", (5, 6, 5, 6, 2), "The Tactician"),
    "lavinho":    ("Lavinho",           "SR",  (5, 5, 6, 3, 3), "The Magician"),
    "blake":      ("Adam Blake",        "SR",  (6, 3, 3, 3, 3), "Power Striker"),
    "cavasoz":    ("Pablo Cavasoz",     "SR",  (5, 6, 6, 3, 6), "The Free Kick Master"),
    "luna":       ("Leonardo Luna",     "SSR", (6, 5, 6, 3, 5), "The Dribbler"),
    "silva":      ("Dada Silva",        "SR",  (6, 3, 5, 3, 2), "The Striker"),

    # ── Japan — Blue Lock ───────────────────────────────────────────────────
    "isagi":      ("Yoichi Isagi",      "SSR", (5, 5, 3, 5, 2), "Spatial Hunter"),
    "rin":        ("Rin Itoshi",        "SSR", (6, 5, 5, 5, 6), "The Complete Striker"),
    "shidou":     ("Ryusei Shidou",     "SSR", (6, 3, 3, 2, 2), "Goal Monster"),
    "barou":      ("Shoei Barou",       "SR",  (6, 2, 5, 3, 3), "The King"),
    "bachira":    ("Meguru Bachira",    "SR",  (5, 5, 6, 2, 3), "Monster's Partner"),
    "chigiri":    ("Hyoma Chigiri",     "SR",  (5, 3, 5, 3, 2), "Pure Speed"),
    "reo":        ("Reo Mikage",        "SR",  (5, 5, 5, 5, 3), "All-Rounder"),
    "kunigami":   ("Rensuke Kunigami",  "SR",  (6, 2, 3, 5, 3), "The Hero"),
    "otoya":      ("Eita Otoya",        "SR",  (3, 3, 5, 2, 2), "Opportunist"),
    "aiku":       ("Oliver Aiku",       "SR",  (2, 3, 3, 6, 2), "The Libero"),
    "karasu":     ("Tabito Karasu",     "SR",  (3, 5, 5, 5, 2), "Field Brain"),
    "gagamaru":   ("Gin Gagamaru",      "R",   (2, 3, 2, 6, 1), "The Wall"),
    "aryu":       ("Jyubei Aryu",       "R",   (2, 3, 2, 6, 2), "Absolute Beauty"),
    "yukimiya":   ("Kenyu Yukimiya",    "SR",  (5, 3, 6, 3, 5), "The Prince"),
    "niko":       ("Ikki Niko",         "R",   (2, 5, 5, 6, 2), "Defensive Anchor"),
    "hiori":      ("Yo Hiori",          "SR",  (3, 6, 5, 3, 3), "Quiet Shadow"),
    "sendo":      ("Shuto Sendo",       "R",   (5, 3, 3, 3, 2), "Wing Forward"),
    "kurona":     ("Ranze Kurona",      "R",   (2, 5, 5, 3, 2), "The Apprentice"),
    "tsurugi":    ("Zantetsu Tsurugi",  "R",   (5, 2, 5, 3, 2), "Sharp Shooter"),
    "fukaku":     ("Gen Fukaku",        "N",   (1, 3, 2, 6, 1), "Defensive Specialist"),
    "raichi":     ("Jingo Raichi",      "R",   (3, 3, 3, 6, 2), "Rage"),
    "kiyora":     ("Jin Kiyora",        "R",   (5, 3, 5, 3, 3), "Midfield Maestro"),
    "nanase":     ("Nijiro Nanase",     "N",   (3, 3, 3, 3, 2), "Utility Player"),

    # ── Other Blue Lock players ─────────────────────────────────────────────
    "nagi":       ("Seishiro Nagi",     "SSR", (6, 5, 5, 2, 2), "Raw Talent"),
    "tokimitsu":  ("Aoshi Tokimitsu",   "R",   (3, 3, 3, 6, 2), "Unchained Power"),
    "nio":        ("Kazuma Nio",        "N",   (2, 3, 3, 6, 2), "Defensive Midfielder"),
    "hiiragi":    ("Reiji Hiiragi",     "R",   (5, 3, 5, 3, 3), "Forward"),
    "wanima":     ("Junichi Wanima",    "N",   (3, 3, 3, 3, 2), "Twin One"),
    "saramadara": ("Kairu Saramadara",  "N",   (3, 3, 3, 3, 2), "Midfielder"),
    "tsunzaki":   ("Taiga Tsunzaki",    "N",   (3, 3, 3, 3, 2), "Midfielder"),
    "nishioka":   ("Hajime Nishioka",   "N",   (3, 3, 3, 3, 2), "Midfielder"),
    "ishikari":   ("Yukio Ishikari",    "N",   (3, 3, 2, 5, 2), "Defensive"),
    "shiguma":    ("Kyohei Shiguma",    "N",   (2, 2, 2, 5, 2), "Defensive"),
    "tanaka":     ("Shingen Tanaka",    "N",   (3, 3, 2, 3, 2), "Midfielder"),
    "endoji":     ("Akira Endoji",      "N",   (3, 3, 3, 3, 2), "Utility"),
    "yuzu":       ("Haruhiko Yuzu",     "N",   (3, 3, 3, 3, 2), "Utility"),
    "cho":        ("Kento Cho",         "N",   (3, 3, 3, 3, 2), "Utility"),
    "igarashi":   ("Gurimu Igarashi",   "N",   (2, 2, 2, 3, 2), "Tryhard"),

    # ── France ──────────────────────────────────────────────────────────────
    "loki":       ("Julian Loki",       "SSR", (6, 5, 6, 3, 3), "The Genius"),
    "chevalier":  ("Charles Chevalier", "SR",  (5, 6, 5, 3, 3), "Playmaker"),
    "hugo":       ("Vivian Hugo",       "SR",  (5, 6, 5, 6, 2), "Box-to-Box"),
    "camus":      ("Camus",             "R",   (5, 3, 5, 2, 2), "Forward"),
    "leyden":     ("Leyden",            "R",   (3, 5, 5, 2, 2), "Midfielder"),
    "bats":       ("Bats",              "N",   (3, 5, 3, 3, 2), "Midfielder"),
    "chapa":      ("Chapa",             "N",   (2, 3, 3, 5, 2), "Defensive"),
    "delon":      ("Delon",             "N",   (2, 3, 3, 5, 2), "Defensive"),
    "hermes":     ("Hermes",            "N",   (2, 3, 3, 5, 2), "Defensive"),
    "gabin":      ("Gabin",             "N",   (2, 3, 3, 5, 2), "Defensive"),
    "renoir":     ("Renoir",            "N",   (1, 3, 2, 6, 1), "Goalkeeper"),

    # ── England ─────────────────────────────────────────────────────────────
    "knight":     ("Teddy Knight",      "SSR", (6, 5, 6, 3, 3), "The Prodigy"),
    "agi":        ("Agi",               "SR",  (5, 5, 3, 3, 2), "Midfielder"),
    "achanpong":  ("Achanpong",         "SR",  (3, 6, 5, 5, 2), "Playmaker"),
    "niang":      ("Niang",             "R",   (3, 5, 5, 3, 2), "Winger"),
    "goodman":    ("Goodman",           "R",   (2, 3, 3, 6, 2), "Defender"),
    "childs":     ("Childs",            "R",   (5, 3, 3, 3, 2), "Forward"),
    "arthur":     ("Arthur",            "N",   (2, 3, 3, 5, 2), "Utility"),
    "rooke":      ("Rooke",             "N",   (1, 3, 2, 6, 1), "Goalkeeper"),

    # ── Foreign Stars / NG11 / NEL ──────────────────────────────────────────
    "sae":        ("Sae Itoshi",        "SSR", (5, 6, 6, 3, 5), "Spain's Genius"),
    "kaiser":     ("Michael Kaiser",    "SSR", (6, 3, 5, 3, 6), "The Emperor"),
    "lorenzo":    ("Don Lorenzo",       "SR",  (3, 5, 6, 6, 2), "Zombie Dribbler"),
    "ness":       ("Alexis Ness",       "SR",  (3, 6, 6, 3, 3), "The Mess"),
    "iglesias":   ("Bunny Iglesias",    "SR",  (6, 3, 3, 3, 3), "The Rabbit"),
    "lara":       ("Ignacio Lara",      "R",   (5, 3, 5, 3, 2), "Forward"),
    "gesner":     ("Erik Gesner",       "N",   (3, 3, 3, 3, 2), "Midfielder"),
    "sachs":      ("Theo Sachs",        "N",   (2, 3, 3, 5, 2), "Defensive"),
    "birkenstock":("Birkenstock",       "N",   (2, 2, 2, 5, 2), "Defensive"),
    "gomez":      ("Gomez",             "N",   (3, 3, 3, 3, 2), "Utility"),
    "bos":        ("Bos",               "N",   (3, 3, 3, 3, 2), "Utility"),
    "uraziz":     ("Uraziz",            "N",   (3, 3, 3, 3, 2), "Utility"),
}

ROLE = {
    "isagi": "MF", "rin": "ST", "sae": "MF", "kaiser": "ST",
    "nagi": "ST", "shidou": "ST", "aiku": "DF", "charles": "MF",
    "barou": "ST", "chigiri": "WF", "bachira": "WF", "reo": "MF",
    "hiori": "MF", "otoya": "WF", "karasu": "MF", "yukimiya": "WF",
    "kunigami": "ST", "ness": "MF", "zantetsu": "WF", "loki": "ST",
    "chevalier": "MF", "knight": "ST",
}

STATS = ("shot", "passing", "dribble", "meta", "freekick")
STAT_NAME = {
    "shot": "Shot", "passing": "Passing", "dribble": "Dribble",
    "meta": "Meta Vision", "freekick": "Free Kick",
}
STAT_ABBR = {
    "shot": "SHO", "passing": "PAS", "dribble": "DRI",
    "meta": "MET", "freekick": "FRK",
}


def _roll_rarity() -> str:
    """Weighted rarity draw. SSR=3 SR=11 R=26 N=42 per 82 total."""
    r = random.randint(1, sum(RARITY_WEIGHT.values()))
    t = 0
    for rarity, w in RARITY_WEIGHT.items():
        t += w
        if r <= t:
            return rarity
    return "N"


# ── helpers ──────────────────────────────────────────────────────────────────

def base_stats(char_key: str) -> dict[str, int]:
    return dict(zip(STATS, ROSTER[char_key][2]))


def epithet_of(char_key: str) -> str:
    return ROSTER[char_key][3]


RARITY_ICON = {"SSR": "✦", "SR": "✶", "R": "◆", "N": "◦"}


def icon_of(char_key: str) -> str:
    return f"{RARITY_ICON.get(rarity_of(char_key), '·')} "


def effective_stats(char_key: str, boosts: dict) -> dict[str, int]:
    base = base_stats(char_key)
    return {s: min(MAX_STAT, base[s] + max(0, min(MAX_BOOST, boosts.get(s, 0)))) for s in STATS}


def stats_of(char_key: str) -> dict[str, int]:
    """Return base stat dict for a character."""
    if char_key not in ROSTER:
        return {s: 1 for s in STATS}
    vals = ROSTER[char_key][2]
    return dict(zip(STATS, vals))


def overall(stats: dict[str, int]) -> int:
    """Overall rating 1–99 based on stats."""
    low = min(sum(v) for _, _, v, _ in ROSTER.values())
    hi  = max(sum(v) for _, _, v, _ in ROSTER.values()) + len(STATS) * MAX_BOOST
    span = hi - low
    scaled = 60 + 39 * (sum(stats.values()) - low) / span
    return max(1, min(99, round(scaled)))


# ── gacha ─────────────────────────────────────────────────────────────────────

def gacha(exclude: set[str]) -> str | None:
    pool = [k for k in ROSTER if k not in exclude]
    if not pool:
        return None
    weights = [RARITY_WEIGHT[rarity_of(k)] for k in pool]
    return random.choices(pool, weights=weights, k=1)[0]


# ── legacy aliases (kept for cross-module compatibility) ─────────────────────

def pull(user_id: int) -> str:
    """Return a char_key. Same player always gets the same result within
    the same season — seeded by user_id so /gacha is always deterministic."""
    rng = random.Random(str(user_id))
    rarity = _roll_rarity()
    pool = [k for k, v in ROSTER.items() if v[1] == rarity]
    if not pool:
        pool = list(ROSTER.keys())
    return rng.choice(pool)


def resolve(needle: str) -> str | None:
    key = needle.strip().lower()
    if key in ROSTER:
        return key
    for char_key, (name, *_) in ROSTER.items():
        tokens = {t.lower() for t in name.split()}
        if key == name.lower() or key in tokens:
            return char_key
    return None


def role_of(char_key: str) -> str:
    return ROLE.get(char_key, "N/A")


def title_of(char_key: str) -> str:
    return ROSTER[char_key][3] if char_key in ROSTER else ""


def rarity_of(char_key: str) -> str:
    return ROSTER[char_key][1] if char_key in ROSTER else "N"


def name_of(char_key: str) -> str:
    return ROSTER[char_key][0] if char_key in ROSTER else char_key