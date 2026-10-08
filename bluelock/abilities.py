from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from . import db
from .config import (
    ABILITY_T1_COST,
    ABILITY_T1_LEVEL,
    ABILITY_T2_COST,
    ABILITY_T2_LEVEL,
    ABILITY_T3_COST,
    ABILITY_T3_LEVEL,
    ABILITY_T4_COST,
    ABILITY_T4_LEVEL,
    ZONE_BOX,
    ZONE_SHOOT,
)

SET_PIECES = ("freekick", "penalty")

PASSIVE_ICON = "🛡"
SKILL_ICON = "⚡"

PASSIVE_CHARGES = 1  # every passive fires ONCE per match (free, one-shot)


def enabled() -> bool:
    from . import config
    return bool(getattr(config, "ABILITIES_ENABLED", True))


@dataclass(frozen=True)
class Ability:
    id: str
    char: str
    kind: str
    tier: int
    name: str
    desc: str
    att: Optional[Callable] = None
    dfd: Optional[Callable] = None
    auto: Optional[str] = None
    when: Optional[Callable] = None
    zone_extra: int = 0
    on_lost: Optional[str] = None
    tackle_keep: bool = False
    save_self: bool = False
    punch_to_self: bool = False
    save_margin: int = 0
    gk_down: int = 0
    die_floor: int = 0
    pen_edge: int = 0
    pen_autoscore: bool = False
    tie_win: bool = False
    pass_buff: int = 0
    # Every player the actor beat PAST takes this amount until the next goal.
    # Applied at the end of resolve() (after any goal he scored), so the
    # debuff survives the goal it was dealt on.
    beats: int = 0
    # Isagi's Last Puzzle: he has already read the field and got on the end of
    # it — the wall cannot stop him and the keeper cannot save it.
    sure_goal: bool = False
    # Arming takes possession the moment the button is pressed — even off a
    # loose ball / the opponent's feet — then the action plays as his own.
    steal_on_arm: bool = False
    contest: Optional[dict] = None
    # On a SUCCESSFUL move the actor carries past up to `through` more
    # opponents. The attack die sets how many (capped), so the count really
    # lands in the 1..N band. Those opponents are marked beaten alongside the
    # normal marker, so `beats` hits every one of them too.
    through: int = 0
    # Goal payout: stashed when the passive fires, paid at the NEXT goal by
    # the owner's team, then cleared. `self` is for the owner; `mate` for the
    # other party of the move (the assister when he scored, the scorer when he
    # assisted).
    goal_self: int = 0
    goal_mate: int = 0
    # A keeper who does not hold on to it: whoever owns this comes for the loose
    # ball instead of the coin flip.
    on_ball_loose: bool = False
    # ...and this one finishes it outright instead of just collecting it.
    finish_loose: bool = False
    # Monster Moment: each dribble he lands tops up a stack that rides on every
    # action of his until the next goal wipes it.
    dribble_stack: int = 0
    # Knight Defense: paid when he wins the ball, rides his possession and dies
    # with it.
    hold_bonus: int = 0
    # Dance: the run he starts on his dribble ends with him walking past the
    # keeper too.
    beat_keeper: bool = False
    aura_gk: int = 0
    gamble: bool = False
    gamble_min: int = 0
    pass_advance: int = 0
    first_free: bool = False
    puppet: bool = False
    # ── Bound ─────────────────────────────────────────────────────────────────
    # bound=True: this ability only works while the owner's Bound partner is on
    # the SAME team in this match (position/adjacency irrelevant). A one-way
    # bound (BUFF) keeps BOTH sides inactive. Numeric effects grow with the
    # Bound tier: +(tier - 1), tier 1 → +0, tier 2 → +1, tier 3 → +2.
    bound: bool = False


def _losing(c):
    return c["diff"] < 0


def _level(c):
    return c["diff"] == 0


def _after_pass(c):
    return c["last_pass"] is not None


def _just_loose(c):
    """He came and picked up a loose ball himself — Barou arrives either way."""
    return (c.get("loose") is not None and c.get("self") is not None
            and c["loose"] == c["self"]["slot"])


def _unmarked(c):
    return c["unmarked"]


def _final(c):
    return c["zone"] >= ZONE_SHOOT


def _mid(c):
    return c["zone"] == 0


def _first_link(c):
    return c["chain"] == 0


def _mate(*keys):
    ks = frozenset(keys)
    return lambda c: bool(ks & c["mates"])


def _foe(*keys):
    ks = frozenset(keys)
    return lambda c: bool(ks & c["foes"])


def _foe_rarity(rarity):
    return lambda c: rarity in c["foe_rarities"]


REGISTRY: dict[str, Ability] = {}


BY_CHAR: dict[str, list[Ability]] = {}
STARTERS: dict[str, list[str]] = {}

from . import abilities_data as _data

_data.register_all()


def validate_contests() -> None:
    allowed = {"win", "zone", "att", "def", "buff", "sure"}
    for aid, ab in REGISTRY.items():
        cfg = ab.contest
        if not cfg:
            continue
        action = cfg.get("action")
        assert isinstance(action, str) or (isinstance(action, tuple) and action), f"{aid}: bad action"
        assert cfg.get("secret") in ("a", "d"), f"{aid}: bad secret"
        a_keys = [k for k, _ in cfg.get("a") or []]
        d_keys = [k for k, _ in cfg.get("d") or []]
        assert len(a_keys) >= 2 and len(d_keys) >= 2, f"{aid}: needs 2+ options per side"
        assert len(set(a_keys)) == len(a_keys), f"{aid}: duplicate option keys"
        assert len(set(d_keys)) == len(d_keys), f"{aid}: duplicate option keys"
        want = {f"{x}_{y}" for x in a_keys for y in d_keys}
        matrix = cfg.get("matrix") or {}
        assert want == set(matrix), f"{aid}: matrix keys {sorted(want ^ set(matrix))}"
        for key, eff in matrix.items():
            assert isinstance(eff, dict) and set(eff) <= allowed, f"{aid}.{key}: {set(eff) - allowed}"
            if "win" in eff:
                assert eff["win"] in ("att", "def"), f"{aid}.{key}: bad win"
            for n in ("zone", "att", "def", "buff", "sure"):
                if n in eff:
                    assert isinstance(eff[n], int), f"{aid}.{key}: {n} must be int"
            if "buff" in eff:
                acts = (action,) if isinstance(action, str) else action
                assert "pass" in acts, f"{aid}.{key}: buff without pass action"


validate_contests()

# ── Taha's cap: 1 passive + 2 skills per character (+ its bound) ──
def _trim_kits() -> None:
    for char, items in BY_CHAR.items():
        own_passives = [a for a in items if a.kind == "passive" and not a.bound]
        skills = [a for a in items if a.kind == "skill"]
        keep = {a.id for a in own_passives[:1] + skills[:2]}
        keep.update(a.id for a in items if a.bound)
        if len(keep) != len(items):
            BY_CHAR[char] = [a for a in items if a.id in keep]
            st = STARTERS.get(char)
            if st:
                STARTERS[char] = [a for a in st if a in keep]


_trim_kits()


CATEGORIES = (
    "read",
    "gamble",
    "steal",
    "rush",
    "finish",
    "pass",
    "penalty",
    "wall",
    "draw",
    "core",
)


def category_of(ab: Ability) -> str:
    if ab.contest:
        return "read"
    if ab.gamble:
        return "gamble"
    if ab.auto == "stop":
        return "steal"
    if ab.auto == "win" or ab.zone_extra:
        return "rush"
    if ab.pen_edge or ab.pen_autoscore:
        return "penalty"
    if ab.pass_buff or ab.pass_advance:
        return "pass"
    if ab.aura_gk or ab.dfd is not None or ab.punch_to_self:
        return "wall"
    if ab.on_lost == "foul":
        return "draw"
    if ab.att is not None or ab.gk_down or ab.save_margin or ab.tie_win or ab.die_floor or ab.save_self or ab.tackle_keep:
        return "finish"
    return "core"


CATEGORY_ICON = {
    "read": "🧠",
    "gamble": "🎲",
    "steal": "🥷",
    "rush": "🌊",
    "finish": "⚽",
    "pass": "✨",
    "penalty": "🥶",
    "wall": "🛡",
    "draw": "🎭",
    "core": "🔁",
}


def sync_catalog() -> int:
    """Mirror the in-memory REGISTRY into the ability_catalog table."""
    with db.tx() as c:
        c.execute("DELETE FROM ability_catalog")
        for ab in REGISTRY.values():
            c.execute(
                "INSERT INTO ability_catalog(id, char, kind, tier, category, name) VALUES(?,?,?,?,?,?)",
                (ab.id, ab.char, ab.kind, ab.tier, category_of(ab), ab.name),
            )
        return len(REGISTRY)


def catalog_stats() -> list[tuple[str, int]]:
    rows = db.q(
        "SELECT category, COUNT(*) AS n FROM ability_catalog GROUP BY category ORDER BY n DESC"
    )
    return [(r["category"], r["n"]) for r in rows]


def get(aid: str) -> Ability | None:
    return REGISTRY.get(aid)


def starter_ids(char_key: str) -> list[str]:
    return list(STARTERS.get(char_key, []))


def kit_for_char(char_key: str) -> list[Ability]:
    return list(BY_CHAR.get(char_key, []))


def price_and_level(ab: Ability) -> tuple[int, int]:
    if ab.tier == 1 and ab.kind == "skill":
        return ABILITY_T1_COST, ABILITY_T1_LEVEL
    if ab.tier == 2:
        return ABILITY_T2_COST, ABILITY_T2_LEVEL
    if ab.tier == 3:
        return ABILITY_T3_COST, ABILITY_T3_LEVEL
    if ab.tier >= 4:
        return ABILITY_T4_COST, ABILITY_T4_LEVEL
    return 0, 1


def owned_ids(user_id: int, char_key: str) -> list[str]:
    owned = set(starter_ids(char_key)) | (db.unlocked_ids(user_id) & {a.id for a in kit_for_char(char_key)})
    ordered = [a.id for a in kit_for_char(char_key)]
    return [aid for aid in ordered if aid in owned]


# ------------------------------------------------------------------ usage model

def usable(state: dict, ab: Ability) -> bool:
    charges = state.setdefault("charges", {})
    spent = state.get("used", [])
    if ab.id in spent:
        return False
    left = charges.get(ab.id)
    if left is None:
        charges[ab.id] = PASSIVE_CHARGES if ab.kind == "passive" else 1
        left = charges[ab.id]
    return left > 0


def consume(state: dict, ab: Ability) -> None:
    charges = state.setdefault("charges", {})
    left = charges.get(ab.id)
    if left is None:
        left = PASSIVE_CHARGES if ab.kind == "passive" else 1
    left -= 1
    charges[ab.id] = left
    if left <= 0:
        state.setdefault("used", []).append(ab.id)


def refund(state: dict, ab: Ability) -> None:
    """Give a charge back — used when a duel is undone before it resolved."""
    used = state.get("used", [])
    if ab.id in used:
        used.remove(ab.id)
    charges = state.setdefault("charges", {})
    charges[ab.id] = charges.get(ab.id, 0) + 1


def arm(state: dict, slot: int, ab: Ability) -> None:
    state.setdefault("armed", {})[str(slot)] = ab.id


def disarm(state: dict, slot: int) -> Ability | None:
    aid = state.get("armed", {}).pop(str(slot), None)
    return get(aid) if aid else None


def peek_armed(state: dict, slot: int) -> Ability | None:
    """The armed skill for a slot; silently drops it if already spent."""
    aid = state.get("armed", {}).get(str(slot))
    if not aid:
        return None
    ab = get(aid)
    if ab is None:
        state.get("armed", {}).pop(str(slot), None)
        return None
    if not usable(state, ab):
        state.get("armed", {}).pop(str(slot), None)
        return None
    return ab


def spend_armed(state: dict, slot: int) -> Ability | None:
    ab = peek_armed(state, slot)
    if ab is not None:
        state.get("armed", {}).pop(str(slot), None)
        consume(state, ab)
    return ab


def note(state: dict, player_name: str, ab: Ability, tail: str = "", icon: str | None = None) -> str:
    mark = icon or (SKILL_ICON if ab.kind == "skill" else PASSIVE_ICON)
    line = f"{mark} <b>{ab.name}</b> — <b>{player_name}</b>"
    if tail:
        line += f" · {tail}"
    state.setdefault("notes", []).append(line)
    return line


def icon_for(ab: Ability) -> str:
    if ab.gamble:
        return "🎲"
    return SKILL_ICON if ab.kind == "skill" else PASSIVE_ICON


def build_ctx(match, roster, self_row, other_row, action: str, zone: int, state: dict) -> dict:
    team = self_row["team"]
    mates = {r["char_key"] for r in roster if r["team"] == team}
    foes = {r["char_key"] for r in roster if r["team"] != team}
    foe_rarities = {rarity_of_key(k) for k in foes}
    s1, s2 = match["score1"], match["score2"]
    diff = (s1 - s2) if team == 1 else (s2 - s1)
    limit = turn_limit_safe(match)
    beaten = state.get("beaten", [])
    return {
        "action": action,
        "zone": zone,
        "chain": state.get("chain", 0),
        "beaten_n": len(beaten),
        "unmarked": other_row is None,
        "last_pass": state.get("last_pass"),
        "loose": state.get("loose_claim_slot"),
        # the stance the player picked when he armed his passive
        "mode": (state.get("modes") or {}).get(str(self_row["slot"])),
        "self": self_row,
        "other": other_row,
        "roster": roster,
        "mates": mates,
        "foes": foes,
        "foe_rarities": foe_rarities,
        "diff": diff,
        "turn": match["turn"],
        "limit": limit,
        "remaining": max(0, limit - match["turn"]),
        "self_goals": self_row["goals"],
        "self_stops": self_row["stops"],
    }


def rarity_of_key(char_key: str | None) -> str:
    if char_key is None:
        return "N"
    from .characters import rarity_of
    return rarity_of(char_key)


def turn_limit_safe(match) -> int:
    from .engine import turn_limit
    return turn_limit(match)


def kits_by_user(roster) -> dict[int, list[Ability]]:
    if not enabled():
        return {}
    out: dict[int, list[Ability]] = {}
    cache: dict[int, list[str]] = {}
    for r in roster:
        uid = r["user_id"]
        if uid is None:
            continue
        if uid not in cache:
            cache[uid] = owned_ids(uid, r["char_key"])
        out[uid] = [get(aid) for aid in cache[uid]]
        out[uid] = [a for a in out[uid] if a]
    return out


def kit_of(kits: dict, row) -> list[Ability]:
    if not enabled() or row is None:
        return []
    return kits.get(row["user_id"], [])
