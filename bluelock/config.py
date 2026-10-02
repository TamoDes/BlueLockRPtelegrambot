import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bluelock.db"
ENV_FILE = BASE_DIR / ".env"
LEGACY_WALLET = BASE_DIR / "wallets.json"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env(ENV_FILE)

BOT_TOKEN = os.environ.get("BLUELOCK_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    sys.exit("Missing BLUELOCK_BOT_TOKEN. Put it in .env before starting.")

ADMINS = {
    name.strip().lstrip("@").lower()
    for name in os.environ.get("BLUELOCK_ADMINS", "thetamo,knight_ozuki,itoshi_rin_org").split(",")
    if name.strip()
}

ADMIN_IDS = {
    int(part)
    for part in os.environ.get("BLUELOCK_ADMIN_IDS", "").replace(";", ",").split(",")
    if part.strip().isdigit()
}

def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw)
    except ValueError:
        return default


SEASON = _int_env("BLUELOCK_SEASON", 1)

# active season phase: 'test' (sandbox, no yen/xp) or 'live' — set from the admin
# panel, persisted in the settings table, read fresh on every payout.
SEASON_PHASE_KEY = "season_phase"


def active_phase() -> str:
    from . import db
    phase = db.get_setting(SEASON_PHASE_KEY)
    if phase not in SEASON_PHASES:
        phase = "test"
    return phase


def test_mode() -> bool:
    """True while the running season is a test/beta season."""
    return is_test_phase(active_phase())

ABILITIES_ENABLED = os.environ.get("BLUELOCK_ABILITIES", "1") not in ("0", "false", "no")

DICE_FACES = 6
DICE_EMOJI = {"🎲"}
DICE_ANIM_SECONDS = 3.6

STATS = ("shot", "passing", "dribble", "meta", "freekick")
STAT_NAME = {
    "shot": "Shot",
    "passing": "Passing",
    "dribble": "Dribble",
    "meta": "Meta Vision",
    "freekick": "Free Kick",
}
STAT_ABBR = {
    "shot": "SHO",
    "passing": "PAS",
    "dribble": "DRI",
    "meta": "MET",
    "freekick": "FRK",
}

KEEPER_NAME = "BlueLock Man"
KEEPER_POWER = 4
KEEPER_CATCH_ROLL = 4
PENALTY_TARGETS = ("left", "center", "right")
PENALTY_NERVE_SPAN = 2

ZONE_NAME = ("Midfield", "Final Third", "Box")
ZONE_BOX = len(ZONE_NAME) - 1
ZONE_SHOOT = 1

GOAL_VALUE = 200_000
ASSIST_VALUE = 150_000
WIN_VALUE = 500_000
DRAW_VALUE = 150_000
PLAY_VALUE = 50_000
# --- seasons (test phase = no yen, no xp) ------------------------------------
SEASON_PHASES = ("test", "live")
TEST_PHASE_TEXT = {
    "test": "🧪 TEST",
    "live": "🏆 LIVE",
}


def phase_label(phase: str) -> str:
    return TEST_PHASE_TEXT.get(phase, TEST_PHASE_TEXT["test"])


def is_test_phase(phase: str) -> bool:
    """Test seasons are sandbox: matches, daily and quests pay no yen/xp."""
    return phase != "live"
MOTM_VALUE = 250_000

REROLL_COST = 1_000_000
TITLE_COST = 2_000_000
TRAIN_BASE = 300_000
MAX_BOOST = 2
MAX_TITLE_LEN = 24
BASE_MAX = 6
MAX_STAT = BASE_MAX + MAX_BOOST
# ── limit system: every 5 levels the player picks ONE limit (max 5 total) ──
LIMIT_LEVELS = (5, 10, 15, 20, 25)
MAX_LIMITS = 5
BOOST_LEVELS = LIMIT_LEVELS  # training slots unlock with the limit picks (5/10/15/20/25)

ABILITY_T2_LEVEL = 15
ABILITY_T2_COST = 1_500_000
ABILITY_T3_LEVEL = 30
ABILITY_T3_COST = 3_000_000
ABILITY_T4_LEVEL = 45
ABILITY_T4_COST = 5_000_000

XP_GOAL = 100
XP_ASSIST = 60
XP_STOP = 30
XP_WIN = 80
XP_DRAW = 40
XP_LOSS = 20
XP_ACTION = 5
XP_PER_LEVEL = 520  # leveled up: 2× harder than before
LEVEL_UP_BONUS = 250_000

# ── bound system: starts at tier 1, upgrades buy a stronger version ────────
BOUND_ENABLED = False  # TEST SEASON: Bound stays off; flip to True for release
MAX_BOUND_TIER = 3
BOUND_TIER_LEVEL = {2: 5, 3: 10}
BOUND_TIER_COST = {2: 1_500_000, 3: 4_000_000}

# ── skill slots: 1 usable skill per match at first, buy the 2nd ────────────
MAX_SKILL_SLOTS = 2
SKILL_SLOT_COST = 2_000_000

SIZES = (1, 2, 3, 4, 5)
MODES = {"ranked": "Ranked"}
GOAL_TARGET = 3
RANKED_TURN_SLACK = 6
LOG_KEEP = 5
RECAP_KEEP = 5
LOBBY_TTL_HOURS = 6
LOBBY_SWEEP_SECONDS = 1800
TURN_SWEEP_SECONDS = 30
AUTO_ROLL_SECONDS = 180
MATCHLOG_KEEP = 100

DAILY_BASE = 50_000
DAILY_STEP = 25_000
DAILY_MAX_STREAK = 7
QUEST_REWARD = 120_000
QUESTS_PER_DAY = 3

RANKS = (
    (1, "Prospect"),
    (5, "Blue Lock Striker"),
    (10, "Top 100"),
    (20, "Top 23"),
    (30, "Neo Egoist"),
    (40, "U-20 Japan"),
    (50, "World Eleven"),
)

RANKS_ICON = {
    "Prospect": "🥚",
    "Blue Lock Striker": "🔵",
    "Top 100": "💠",
    "Top 23": "⭐",
    "Neo Egoist": "🔥",
    "U-20 Japan": "🐉",
    "World Eleven": "👑",
}

RARITY_WEIGHT = {"SSR": 3, "SR": 11, "R": 26, "N": 42}
RARITY_MARK = {"SSR": "✦SSR", "SR": "✦SR", "R": "R", "N": "N"}


def max_turns(size: int, mode: str = "ranked") -> int:
    base = 8 + 4 * size
    return base * RANKED_TURN_SLACK if mode == "ranked" else base


MAX_LEVEL = 60


def rank_for(level: int) -> tuple[str, str]:
    label = RANKS[0][1]
    for need, name in RANKS:
        if level >= need:
            label = name
    return label, RANKS_ICON[label]


def xp_for_level(level: int) -> int:
    steps = max(0, level - 1)
    return XP_PER_LEVEL * steps + 20 * steps * steps


def level_for(xp: int) -> int:
    if xp <= 0:
        return 1
    disc = XP_PER_LEVEL * XP_PER_LEVEL + 80 * xp
    raw = (-XP_PER_LEVEL + (disc ** 0.5)) / 40
    return min(MAX_LEVEL, int(raw) + 1)


def boosts_allowed(level: int) -> int:
    return sum(1 for need in BOOST_LEVELS if level >= need)


def train_cost(current_boost: int) -> int:
    return TRAIN_BASE * (current_boost + 1) * 3
