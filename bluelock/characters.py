import random
from pathlib import Path

from .config import BASE_DIR, BASE_MAX, MAX_BOOST, MAX_STAT, RARITY_WEIGHT, STATS

CHIBI_DIR = BASE_DIR / "playerchibiicons"


def chibi_path(char_key: str) -> Path | None:
    p = CHIBI_DIR / f"{char_key}.png"
    return p if p.is_file() else None

# (name, rarity, (shot, passing, dribble, meta, freekick), title)
# skills/passives: filled per-character by abilities_data.py
ROSTER = {
    # ── Nigeria ──────────────────────────────────────────────────────────────
    "kuso":       ("Godwin Kuso",       "SR",  (2, 4, 3, 3, 1), "Tempo Controller"),
    "umaru":      ("Umaru",             "N",   (3, 2, 2, 2, 1), "Forward"),
    
    # ── Master Strikers / World Five ────────────────────────────────────────
    "noa":        ("Noel Noa",          "SSR", (4, 3, 3, 3, 2), "The Strongest"),
    "prince":     ("Chris Prince",      "SSR", (4, 2, 3, 3, 3), "The Prince"),
    "snuffy":     ("Marc Snuffy",       "SSR", (3, 4, 3, 4, 1), "The Tactician"),
    "lavinho":    ("Lavinho",           "SR",  (3, 3, 4, 2, 2), "The Magician"),
    "blake":      ("Adam Blake",        "SR",  (4, 2, 2, 2, 2), "Power Striker"),
    "cavasoz":    ("Pablo Cavasoz",     "SR",  (3, 4, 4, 2, 4), "The Free Kick Master"),
    "luna":       ("Leonardo Luna",     "SSR", (4, 3, 4, 2, 3), "The Dribbler"),
    "silva":      ("Dada Silva",        "SR",  (4, 2, 3, 2, 1), "The Striker"),
    
    # ── Japan — Blue Lock ───────────────────────────────────────────────────
    "isagi":      ("Yoichi Isagi",      "SSR", (3, 3, 2, 3, 1), "Spatial Hunter"),
    "rin":        ("Rin Itoshi",        "SSR", (4, 3, 3, 3, 4), "The Complete Striker"),
    "shidou":     ("Ryusei Shidou",     "SSR", (4, 2, 2, 1, 1), "Goal Monster"),
    "barou":      ("Shoei Barou",       "SR",  (4, 1, 3, 2, 2), "The King"),
    "bachira":    ("Meguru Bachira",    "SR",  (3, 3, 4, 1, 2), "Monster's Partner"),
    "chigiri":    ("Hyoma Chigiri",     "SR",  (3, 2, 3, 2, 1), "Pure Speed"),
    "reo":        ("Reo Mikage",        "SR",  (3, 3, 3, 3, 2), "All-Rounder"),
    "kunigami":   ("Rensuke Kunigami",  "SR",  (4, 1, 2, 3, 2), "The Hero"),
    "otoya":      ("Eita Otoya",        "SR",  (2, 2, 3, 1, 1), "Opportunist"),
    "aiku":       ("Oliver Aiku",       "SR",  (1, 2, 2, 4, 1), "The Libero"),
    "karasu":     ("Tabito Karasu",     "SR",  (2, 3, 3, 3, 1), "Field Brain"),
    "gagamaru":   ("Gin Gagamaru",      "R",   (1, 2, 1, 4, 0), "The Wall"),
    "aryu":       ("Jyubei Aryu",       "R",   (1, 2, 1, 4, 1), "Absolute Beauty"),
    "yukimiya":   ("Kenyu Yukimiya",    "SR",  (3, 2, 4, 2, 3), "The Prince"),
    "niko":       ("Ikki Niko",         "R",   (1, 3, 2, 4, 1), "Defensive Anchor"),
    "hiori":      ("Yo Hiori",          "SR",  (2, 4, 3, 2, 2), "Quiet Shadow"),
    "sendo":      ("Shuto Sendo",       "R",   (3, 2, 2, 2, 1), "Wing Forward"),
    "kurona":     ("Ranze Kurona",      "R",   (1, 3, 3, 2, 1), "The Apprentice"),
    "fukaku":     ("Gen Fukaku",        "N",   (0, 2, 1, 4, 0), "Defensive Specialist"),
    "raichi":     ("Jingo Raichi",      "R",   (2, 2, 2, 4, 1), "Rage"),
    "kiyora":     ("Jin Kiyora",        "R",   (3, 2, 3, 2, 2), "Midfield Maestro"),
    "nanase":     ("Nijiro Nanase",     "N",   (2, 2, 2, 2, 1), "Utility Player"),
    
    # ── Other Blue Lock players ─────────────────────────────────────────────
    "nagi":       ("Seishiro Nagi",     "SSR", (4, 3, 3, 1, 1), "Raw Talent"),
    "kira":       ("Ryosuke Kira",      "N",   (3, 2, 2, 2, 1), "Fallen Star"),
    "charles":    ("Charles Chevalier", "SSR", (3, 4, 3, 2, 2), "France's Trump"),
    "iemon":      ("Okuhito Iemon",     "R",   (1, 2, 2, 3, 1), "Midfield Anchor"),
    "zantetsu":   ("Zantetsu Tsurugi",  "SR",  (3, 1, 3, 2, 1), "Blade of Speed"),
    "naruhaya":   ("Asahi Naruhaya",    "R",   (2, 2, 3, 1, 1), "Pressing Forward"),
    "wanima_a":   ("Keisuke Wanima",    "N",   (2, 2, 2, 2, 1), "Twin One"),
    "wanima_j":   ("Junichi Wanima",    "N",   (2, 2, 2, 2, 1), "Twin Two"),
    "igaguri":    ("Gurimu Igaguri",    "N",   (1, 1, 2, 2, 1), "The Fighter"),
    "tokimitsu":  ("Aoshi Tokimitsu",   "R",   (2, 2, 2, 4, 1), "Iron Body"),
    "nio":        ("Kazuma Nio",        "R",   (1, 2, 2, 4, 1), "The Strategist"),
    "hiiragi":    ("Reiji Hiiragi",     "R",   (3, 2, 3, 2, 2), "Playmaker"),
    "saramadara": ("Kairu Saramadara",  "N",   (2, 2, 2, 2, 1), "Midfielder"),
    "tsunzaki":   ("Taiga Tsunzaki",    "N",   (2, 2, 2, 2, 1), "Midfielder"),
    "nishioka":   ("Hajime Nishioka",   "N",   (2, 2, 2, 2, 1), "Midfielder"),
    "ishikari":   ("Yukio Ishikari",    "N",   (2, 2, 1, 3, 1), "Defensive"),
    "shiguma":    ("Kyohei Shiguma",    "N",   (2, 1, 1, 3, 1), "Defensive"),
    "tanaka":     ("Shingen Tanaka",    "N",   (2, 1, 2, 2, 1), "Midfielder"),
    "endoji":     ("Akira Endoji",      "N",   (2, 2, 2, 2, 1), "Utility"),
    "yuzu":       ("Haruhiko Yuzu",     "N",   (2, 2, 2, 2, 1), "Utility"),
    "cho":        ("Kento Cho",         "N",   (2, 2, 2, 2, 1), "Utility"),
    "igarashi":   ("Gurimu Igarashi",   "N",   (1, 1, 2, 2, 1), "Tryhard"),
    
    # ── France ──────────────────────────────────────────────────────────────
    "loki":       ("Julian Loki",       "SSR", (4, 3, 4, 2, 2), "The Genius"),
    "chevalier":  ("Charles Chevalier", "SR",  (3, 4, 3, 2, 2), "Playmaker"),
    "hugo":       ("Vivian Hugo",       "SR",  (3, 4, 3, 4, 1), "Box-to-Box"),
    "camus":      ("Camus",             "R",   (3, 2, 3, 1, 1), "Forward"),
    "leyden":     ("Leyden",            "R",   (2, 3, 3, 1, 1), "Midfielder"),
    "bats":       ("Bats",              "N",   (2, 3, 2, 2, 1), "Midfielder"),
    "chapa":      ("Chapa",             "N",   (1, 2, 2, 3, 1), "Defender"),
    "delon":      ("Delon",             "N",   (1, 2, 2, 3, 1), "Defender"),
    "hermes":     ("Hermes",            "N",   (1, 2, 2, 3, 1), "Defender"),
    "gabin":      ("Gabin",             "N",   (1, 2, 2, 3, 1), "Defender"),
    "renoir":     ("Renoir",            "N",   (0, 2, 1, 4, 0), "Wall"),
    
    # ── England ─────────────────────────────────────────────────────────────
    "knight":     ("Teddy Knight",      "SSR", (4, 3, 4, 2, 2), "The Captain"),
    "agi":        ("Agi",               "SR",  (3, 3, 2, 2, 1), "Dribbler"),
    "achanpong":  ("Achanpong",         "SR",  (2, 4, 3, 3, 1), "Playmaker"),
    "niang":      ("Niang",             "R",   (2, 3, 3, 2, 1), "Forward"),
    "goodman":    ("Goodman",           "R",   (1, 2, 2, 4, 1), "Defender"),
    "childs":     ("Childs",            "R",   (3, 2, 2, 2, 1), "Forward"),
    "arthur":     ("Arthur",            "N",   (1, 2, 2, 3, 1), "Defender"),
    "rooke":      ("Rooke",             "N",   (0, 2, 1, 4, 0), "Wall"),
    
    # ── Germany ─────────────────────────────────────────────────────────────
    "sae":        ("Sae Itoshi",        "SSR", (3, 4, 4, 2, 3), "The Prodigy"),
    "kaiser":     ("Michael Kaiser",    "SSR", (4, 2, 3, 2, 4), "The Emperor"),
    "lorenzo":    ("Don Lorenzo",       "SR",  (2, 3, 4, 4, 1), "The King"),
    "ness":       ("Alexis Ness",       "SR",  (2, 4, 4, 2, 2), "The Magician"),
    "iglesias":   ("Bunny Iglesias",    "SR",  (4, 2, 2, 2, 2), "Power Striker"),
    "lara":       ("Ignacio Lara",      "R",   (3, 2, 3, 2, 1), "Midfielder"),
    "gesner":     ("Erik Gesner",       "N",   (2, 2, 3, 2, 1), "Midfielder"),
    "sachs":      ("Theo Sachs",        "N",   (1, 2, 2, 3, 1), "Defender"),
    "birkenstock":("Birkenstock",       "N",   (1, 2, 1, 3, 1), "Defender"),
    "gomez":      ("Gomez",             "N",   (2, 2, 2, 2, 1), "Midfielder"),
    "bos":        ("Bos",               "N",   (2, 2, 2, 2, 1), "Midfielder"),
    "uraziz":     ("Uraziz",            "N",   (2, 2, 2, 2, 1), "Midfielder"),
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
        if key == name.lower():
            return char_key
        tokens = {t.lower() for t in name.split()}
        if key in tokens and len(tokens) == 1:
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