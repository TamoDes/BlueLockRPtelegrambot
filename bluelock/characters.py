import random
from pathlib import Path

from .config import BASE_DIR, BASE_MAX, MAX_BOOST, MAX_STAT, RARITY_WEIGHT, STATS

CHIBI_DIR = BASE_DIR / "playerchibiicons"


def chibi_path(char_key: str) -> Path | None:
    p = CHIBI_DIR / f"{char_key}.png"
    return p if p.is_file() else None

ROSTER = {
    # SHO PAS DRI MET FRK — rebased on canon: isagi = meta-vision brain who grew
    # into finishing, rin/sae = complete forwards, masters own the set pieces.
    "isagi":     ("Yoichi Isagi",      "SSR", (5, 4, 3, 6, 2), "Spatial Hunter"),
    "rin":       ("Rin Itoshi",        "SSR", (6, 5, 5, 5, 4), "The Complete Striker"),
    "sae":       ("Sae Itoshi",        "SSR", (4, 6, 5, 5, 4), "Spain's Genius"),
    "kaiser":    ("Michael Kaiser",    "SSR", (6, 4, 4, 4, 5), "The Emperor"),
    "nagi":      ("Seishiro Nagi",     "SSR", (5, 3, 6, 4, 2), "Raw Talent"),
    "shidou":    ("Ryusei Shidou",     "SSR", (6, 2, 5, 4, 3), "Goal Monster"),
    "aiku":      ("Oliver Aiku",       "SSR", (4, 5, 3, 6, 3), "The Unbreakable"),
    "charles":   ("Charles Chevalier", "SSR", (3, 6, 5, 4, 3), "France's Trump"),
    "barou":     ("Shoei Barou",       "SR",  (6, 2, 4, 4, 3), "The King"),
    "chigiri":   ("Hyoma Chigiri",     "SR",  (4, 3, 6, 3, 2), "Pure Speed"),
    "bachira":   ("Meguru Bachira",    "SR",  (4, 4, 6, 3, 2), "Monster's Partner"),
    "reo":       ("Reo Mikage",        "SR",  (4, 4, 4, 4, 3), "All-Rounder"),
    "hiori":     ("Yo Hiori",          "SR",  (3, 6, 3, 5, 3), "Quiet Shadow"),
    "otoya":     ("Eita Otoya",        "SR",  (4, 3, 5, 4, 2), "Opportunist"),
    "karasu":    ("Tabito Karasu",     "SR",  (3, 5, 4, 5, 3), "Field Brain"),
    "yukimiya":  ("Kenyu Yukimiya",    "SR",  (4, 4, 5, 3, 4), "The Prince"),
    "kunigami":  ("Rensuke Kunigami",  "SR",  (5, 2, 3, 3, 5), "The Hero"),
    "ness":      ("Alexis Ness",       "SR",  (3, 5, 4, 4, 4), "Kaiser's Shadow"),
    "zantetsu":  ("Zantetsu Tsurugi",  "SR",  (4, 3, 6, 3, 3), "Blade of Speed"),
    "aryu":      ("Jyubei Aryu",       "R",   (3, 3, 3, 4, 3), "Absolute Beauty"),
    "gagamaru":  ("Gin Gagamaru",      "R",   (2, 2, 3, 6, 3), "The Wall"),
    "raichi":    ("Jingo Raichi",      "R",   (4, 2, 3, 4, 3), "Rage"),
    "iemon":     ("Okuhito Iemon",     "R",   (2, 4, 3, 4, 3), "Midfield Anchor"),
    "naruhaya":  ("Asahi Naruhaya",    "R",   (3, 3, 4, 3, 3), "Agile"),
    "kurona":    ("Ranze Kurona",      "R",   (2, 3, 5, 3, 3), "The Apprentice"),
    "tokimitsu": ("Aoshi Tokimitsu",   "R",   (5, 1, 2, 4, 3), "Unchained Power"),
    "hyoma_k":   ("Nijiro Nanase",     "R",   (3, 3, 4, 4, 2), "The Support"),
    "yuki":      ("Ikki Niko",         "R",   (2, 3, 3, 6, 2), "Quiet"),
    "wanima_a":  ("Keisuke Wanima",    "N",   (2, 2, 4, 3, 2), "Twin One"),
    "wanima_j":  ("Junichi Wanima",    "N",   (2, 4, 2, 3, 2), "Twin Two"),
    "igaguri":   ("Gurimu Igaguri",    "N",   (2, 3, 2, 4, 2), "The Tryhard"),
    "kira":      ("Ryosuke Kira",      "N",   (4, 2, 2, 3, 2), "Fallen Star"),
}

ROLE = {
    "isagi":     "Anchor Striker",
    "rin":       "Complete Forward",
    "sae":       "Playmaker",
    "kaiser":    "Target Striker",
    "nagi":      "Trap Forward",
    "shidou":    "Poacher",
    "barou":     "Lone Striker",
    "chigiri":   "Speedster Winger",
    "bachira":   "Dribbler",
    "reo":       "Utility Ace",
    "hiori":     "Deep-Lying Passer",
    "otoya":     "Shadow Striker",
    "karasu":    "Defensive Brain",
    "yukimiya":  "Wing Dribbler",
    "kunigami":  "Power Forward",
    "aiku":      "Central Defender",
    "charles":   "Deep Playmaker",
    "ness":      "Attacking Midfielder",
    "zantetsu":  "Speed Winger",
    "aryu":      "Aerial Specialist",
    "gagamaru":  "Sweeper",
    "raichi":    "Destroyer",
    "iemon":     "Holding Midfielder",
    "naruhaya":  "Pressing Forward",
    "kurona":    "Box-to-Box Runner",
    "tokimitsu": "Bulldozer",
    "wanima_a":  "Overlap Wingback",
    "wanima_j":  "Overlap Wingback",
    "igaguri":   "Grafting Midfielder",
    "hyoma_k":   "Wide Supplier",
    "yuki":      "Reading Defender",
    "kira":      "Second Striker",
}


def base_stats(char_key: str) -> dict[str, int]:
    return dict(zip(STATS, ROSTER[char_key][2]))


def name_of(char_key: str) -> str:
    return ROSTER[char_key][0]


def rarity_of(char_key: str) -> str:
    return ROSTER[char_key][1]


RARITY_ICON = {"SSR": "✦", "SR": "✶", "R": "◆", "N": "◦"}


def icon_of(char_key: str) -> str:
    return f"{RARITY_ICON.get(rarity_of(char_key), '·')} "


def epithet_of(char_key: str) -> str:
    return ROSTER[char_key][3]


def role_of(char_key: str) -> str:
    return ROLE.get(char_key, "Footballer")


def effective_stats(char_key: str, boosts: dict) -> dict[str, int]:
    base = base_stats(char_key)
    return {s: min(MAX_STAT, base[s] + max(0, min(MAX_BOOST, boosts.get(s, 0)))) for s in STATS}


OVR_FLOOR = min(sum(entry[2]) for entry in ROSTER.values())
OVR_CEIL = max(sum(entry[2]) for entry in ROSTER.values()) + len(STATS) * MAX_BOOST


def overall(stats: dict[str, int]) -> int:
    span = OVR_CEIL - OVR_FLOOR
    scaled = 60 + 39 * (sum(stats.values()) - OVR_FLOOR) / span
    return max(1, min(99, round(scaled)))


def gacha(exclude: set[str]) -> str | None:
    pool = [k for k in ROSTER if k not in exclude]
    if not pool:
        return None
    weights = [RARITY_WEIGHT[rarity_of(k)] for k in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def resolve(needle: str) -> str | None:
    key = needle.strip().lower()
    if key in ROSTER:
        return key
    for char_key, (name, *_) in ROSTER.items():
        tokens = {t.lower() for t in name.split()}
        if key == name.lower() or key in tokens:
            return char_key
    return None


assert all(
    len(stats) == len(STATS) and all(1 <= v <= BASE_MAX for v in stats)
    for _, _, stats, _ in ROSTER.values()
)

assert all(len({name.lower() for (name, *_ ) in ROSTER.values()}) == len(ROSTER) for _ in [0])
