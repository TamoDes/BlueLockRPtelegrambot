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
class PassiveDef:
    """
    One-time-per-match passive effect, free for all characters.

    trigger : what game event fires this passive.
    effect  : what the passive does when it fires.

    Triggers:
      on_pass        — fires after a successful completed pass by this char
      on_dribble     — fires after a successful dribble (actor beat defender)
      on_shot        — fires just before the shot resolution roll
      on_miss        — fires after a missed shot / save
      on_goal        — fires after this char scores
      on_assist      — fires after this char makes an assist
      on_steal       — fires after this char wins a tackle / intercept
      on_pos         — fires every turn: the char is in the right spot

    Effects resolve in order.  "guaranteed_*" effects bypass normal rolls.
    """
    trigger: str          # e.g. "on_pass"
    desc_extra: str = ""  # shown in profile/kit page next to the passive name

    # who receives the buff/stack (None = self, "last_pass" = pass receiver)
    buff_receiver: str | None = None
    buff_amount: int = 0

    # extra dice: add this many extra dice to the triggering action
    extra_dice: int = 0

    # stack: add this many temp dice to the *next* shot by this char (persists)
    stack_next_shot: int = 0

    # guaranteed outcomes (bypass all rolls, GK has zero chance)
    guaranteed_dribble: bool = False  # beat marker with no roll
    guaranteed_shot: bool = False     # shot bypasses keeper roll entirely
    guaranteed_goal: bool = False     # instant goal, no keeper
    guaranteed_pass: bool = False     # pass can't be intercepted
    guaranteed_steal: bool = False    # tackle wins with no roll

    # fake wall: pick N dice to discard after seeing the pool
    fake_wall_dice: int = 0

    # on_miss recovery: when shot misses, who gets the loose ball
    miss_loose_to: str | None = None  # "self" | "team" | "any"

    # position-swap: swap slot with another on the trigger
    swap_with_slot: int | None = None
    swap_if_unmarked: bool = False    # only swap if currently unmarked

    # ── Bound system ─────────────────────────────────────────────────────────────
    bound_type: str | None = None      # "bound" = only works when bound+same-team | None = always
    bound_tier: int = 1                # 1=basic, 2=mid, 3=full. evolves with level-up purchase.

    # ── Target ──────────────────────────────────────────────────────────────────
    target_is_defender: bool = False   # if True, buffs go to the DEFENDER instead of actor
    target_is_teammate: bool = False    # if True, buffs go to the teammate in front
    teammate_approaching: bool = False # passive fires when a teammate with ball is approaching actor

    # ── Temp buffs (one-action duration) ───────────────────────────────────────
    temp_buff_to_actor: int = 0        # buff to actor's next action only
    temp_buff_to_defender: int = 0     # debuff to defender (negative = debuff)

    # ── Conditional triggers ────────────────────────────────────────────────────
    requires_ball_loose: bool = False  # only fires when ball is loose (not held)
    requires_teammate_in_front: bool = False  # only fires if teammate is ahead in attack direction
    on_my_turn_start: bool = False    # fires at start of actor's turn (on_pos trigger)
    on_ball_loose: bool = False        # fires when ball becomes loose
    on_pass_incoming: bool = False     # fires when a pass toward actor is in-flight
    on_teammate_approaching: bool = False  # fires when teammate with ball is nearby
    on_defender_guess: bool = False    # fires when defender is about to guess
    on_match_end: bool = False         # fires at match end
    on_goal_scored: bool = False       # fires when a goal is scored (any char)

    # ── Special effects ────────────────────────────────────────────────────────
    no_keeper_luck: bool = False       # keeper cannot get lucky on this passive's guaranteed_* effects
    wrong_guess_guaranteed: bool = False  # if opponent guesses wrong, guaranteed pass/goal
    guess_three_dice: bool = False     # Hogo-style: 3 dice, 1 real + 1 fake, defender picks
    multi_target_pass: int = 0         # pass through N opponents with bonus
    multi_target_dribble: int = 0      # dribble through N opponents with bonus
    multi_target_shot: int = 0         # shoot through N opponents with bonus
    chain_bonus: int = 0               # bonus if ball was already advanced N zones
    guaranteed_if_keeper_miss: bool = False  # if keeper rolls 1-2, guaranteed goal


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
    # debuff survives the goal it was dealt on — Taha: "تا گل بعدی".
    beats: int = 0
    # "از بین یک الی N نفر": on a SUCCESSFUL move the actor carries past up to
    # `through` more opponents. The attack die sets how many (capped), so the
    # count really lands in the 1..N band. Those opponents are marked beaten
    # alongside the normal marker, so `beats` hits every one of them too.
    through: int = 0
    # Goal payout (Taha's "اگ گل شد ... میگیره"): stashed when the passive
    # fires, paid at the NEXT goal by the owner's team, then cleared. `self` is
    # for the owner; `mate` for the other party of the move (the assister when
    # he scored, the scorer when he assisted).
    goal_self: int = 0
    goal_mate: int = 0
    aura_gk: int = 0
    gamble: bool = False
    gamble_min: int = 0
    manual: bool = False           # True = player must /use before it triggers; charge lasts until first goal
    long_shot: bool = False
    pass_advance: int = 0
    first_free: bool = False
    puppet: bool = False
    passive: "PassiveDef | None" = None
    # ── Bound ─────────────────────────────────────────────────────────────────
    # bound=True: this ability only works while the owner's Bound partner is on
    # the SAME team in this match (position/adjacency irrelevant). A one-way
    # bound (BUFF) keeps BOTH sides inactive. Numeric effects grow with the
    # Bound tier: +(tier - 1), tier 1 → +0, tier 2 → +1, tier 3 → +2.
    bound: bool = False

    # ── Passive resolver ─────────────────────────────────────────────────────────

    def resolve_passive(
        trigger: str,
        actor: dict,
        ctx: dict,
        state: dict,
        out: dict,
    ) -> None:
        """
        Check every passive on `actor` that matches `trigger` and apply effects.

        Hook this at key moments in resolve_action():
          - on_pass   : after pass completes (actor just passed)
          - on_dribble: after dribble resolves (actor beat defender)
          - on_shot   : before shot roll (actor is shooter)
          - on_miss   : after shot is saved / punched
          - on_goal   : after goal is scored (actor is scorer)
          - on_assist : after goal where actor was the passer
          - on_steal  : after actor wins a tackle/intercept
        """
        row = ctx["self"]
        uid = row.get("user_id")
        if uid is None:
            return

        for ab in _passives_of(uid, row["char_key"]):
            p = ab.passive
            if p is None:
                continue
            if p.trigger != trigger:
                continue
            if not _passive_usable(state, ab):
                continue

            # ── apply effects ──────────────────────────────────────────
            _apply_passive(p, actor, ctx, state, out)

            # mark as used (one-time per match)
            _spend_passive(state, ab)


    def _apply_passive(p: PassiveDef, actor: dict, ctx: dict, state: dict, out: dict) -> None:
        """Apply all effects of one PassiveDef."""
        notes: list[str] = []
        note = lambda msg: notes.append(msg)

        if p.guaranteed_dribble:
            out["passive_guaranteed_dribble"] = True
            note(f"🛡 {actor['name']} — guaranteed dribble")

        if p.guaranteed_pass:
            out.setdefault("passive_guaranteed", []).append("pass")
            note(f"✨ {actor['name']} — guaranteed pass")

        if p.guaranteed_steal:
            out["passive_guaranteed_steal"] = True
            note(f"🛡 {actor['name']} — guaranteed steal")

        if p.extra_dice:
            out["passive_extra_dice"] = out.get("passive_extra_dice", 0) + p.extra_dice
            note(f"🎲 {actor['name']} — +{p.extra_dice} dice")

        if p.stack_next_shot:
            state.setdefault("passive_stacks", {})[actor["slot"]] = (
                state["passive_stacks"].get(actor["slot"], 0) + p.stack_next_shot
            )
            note(f"⬆️  {actor['name']} — +{p.stack_next_shot} next shot")

        if p.guaranteed_shot:
            out["passive_guaranteed_shot"] = True
            note(f"⚽ {actor['name']} — guaranteed shot")

        if p.guaranteed_goal:
            out["passive_guaranteed_goal"] = True
            note(f"🏆 {actor['name']} — guaranteed goal")

        if p.fake_wall_dice:
            out["passive_fake_wall"] = out.get("passive_fake_wall", 0) + p.fake_wall_dice
            note(f"🎭 {actor['name']} — fake wall ×{p.fake_wall_dice}")

        if p.buff_amount:
            target_slot = _buff_target(p, actor, ctx, out)
            _grant_passive_buff(target_slot, p.buff_amount, actor, state)
            note(f"✨ {actor['name']} → +{p.buff_amount} [{p.buff_receiver or 'self'}]")

        if p.swap_with_slot is not None:
            out["passive_swap_slot"] = p.swap_with_slot
            out["passive_swap_if_unmarked"] = p.swap_if_unmarked
            note(f"🔄 {actor['name']} — position swap")

        if notes:
            state.setdefault("notes", []).extend(notes)


    def _buff_target(p: PassiveDef, actor: dict, ctx: dict, out: dict) -> int:
        """Resolve who receives the passive buff."""
        if p.buff_receiver == "last_pass":
            slot = out.get("receiver", {}).get("slot")
            if slot is None:
                slot = state.get("last_pass")
            return slot if slot is not None else actor["slot"]
        return actor["slot"]


    def _grant_passive_buff(slot: int, amount: int, actor: dict, state: dict) -> None:
        state.setdefault("buffs", []).append({
            "slot": slot,
            "amt": amount,
            "src": "passive",
            "from": actor["name"],
            "temp": True,   # consumed after one action
        })


    # ── helpers ──────────────────────────────────────────────────────────────────

    def _passives_of(uid: int, char_key: str) -> list[Ability]:
        """Return passive Abilities owned by this user for this character."""
        if not enabled():
            return []
        ids = owned_ids(uid, char_key)
        return [get(aid) for aid in ids if aid and get(aid).kind == "passive" and get(aid).passive is not None]

    def _passive_usable(state: dict, ab: Ability) -> bool:
        if ab is None or ab.passive is None:
            return False
        used: list = state.setdefault("passive_used", [])
        if ab.id in used:
            return False
        return True

    def _spend_passive(state: dict, ab: Ability) -> None:
        state.setdefault("passive_used", []).append(ab.id)


    def reset_passive_state(state: dict) -> None:
        """Called at match start — no extra reset needed (passive_used = [] in new state)."""
        state.setdefault("passive_used", [])
        state.setdefault("passive_stacks", {})


def _losing(c):
    return c["diff"] < 0


def _level(c):
    return c["diff"] == 0


def _ahead(c):
    return c["diff"] > 0


def _after_pass(c):
    return c["last_pass"] is not None


def _unmarked(c):
    return c["unmarked"]


def _box(c):
    return c["zone"] >= ZONE_BOX


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


def _late(c):
    return c["remaining"] <= max(1, c["limit"] // 4)


REGISTRY: dict[str, Ability] = {}


def _reg(ab: Ability) -> Ability:
    REGISTRY[ab.id] = ab
    return ab


BY_CHAR: dict[str, list[Ability]] = {}
STARTERS: dict[str, list[str]] = {}

_KITS = [
    # ---------------------------------------------------------------- SSR
    ("isagi", [
        _reg(Ability("isagi_p1", "isagi", "passive", 1, "Last Puzzle",
            "+2 Shot once a defender has been beaten this attack.",
            att=lambda c: 2 if c["action"] == "shoot" and c["beaten_n"] >= 1 else 0)),
        _reg(Ability("isagi_s1", "isagi", "skill", 1, "Meta Vision Read",
            "While marking: intercept an opponent pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("isagi_p2", "isagi", "passive", 2, "Devour the Stage",
            "First field-duel loss each match doesn't count — he keeps the ball.",
            first_free=True)),
        _reg(Ability("isagi_s2", "isagi", "skill", 3, "Checkmate Finish",
            "Shot scores even if the keeper is within 1 of his total.",
            save_margin=1, when=lambda c: c["action"] == "shoot")),
    ]),
    ("rin", [
        _reg(Ability("rin_p1", "rin", "passive", 1, "Puppet",
            "Guaranteed pass \u2192 the receiver is forced to dribble \u2192 Rin takes the ball "
            "back as if he beat a defender (+2 Shoot / receiver +1 until each scores; "
            "Rin's goal then pays +1 to him and the helper).",
            auto="win", puppet=True, when=lambda c: c["action"] == "pass")),
        _reg(Ability("rin_s1", "rin", "skill", 1, "Perfect Form",
            "His shot beats the marker with no roll.",
            auto="win", when=lambda c: c["action"] == "shoot")),
        _reg(Ability("rin_p2", "rin", "passive", 2, "Bloodline Rivalry",
            "+2 attack if Isagi is on his team; +2 Meta Vision against Sae.",
            att=lambda c: 2 if _mate("isagi")(c) else 0,
            dfd=lambda c: 2 if _foe("sae")(c) else 0)),
        _reg(Ability("rin_s2", "rin", "skill", 3, "Itoshi Curl",
            "+3 Free Kick; ties on his direct free kicks go his way.",
            att=lambda c: 3 if c["action"] == "freekick" else 0,
            tie_win=True, when=lambda c: c["action"] == "freekick")),
    ]),
    ("sae", [
        _reg(Ability("sae_p1", "sae", "passive", 1, "Winning Movement",
            "+2 on his pass; the receiver's next action +2. If a goal follows, "
            "Sae and the scorer each take +1.",
            att=lambda c: 2 if c["action"] == "pass" else 0, pass_buff=2,
            goal_self=1, goal_mate=1,
            when=lambda c: c["action"] == "pass")),
        _reg(Ability("sae_s1", "sae", "skill", 1, "Maestro's Through Ball",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2)),
        _reg(Ability("sae_p2", "sae", "passive", 2, "Possession Metronome",
            "+1 to all duels while his team isn't trailing.",
            att=lambda c: 1 if not _losing(c) else 0)),
        _reg(Ability("sae_s2", "sae", "skill", 3, "Genius Arc",
            "Free kick +3, keeper −2.",
            att=lambda c: 3 if c["action"] == "freekick" else 0, gk_down=2,
            when=lambda c: c["action"] == "freekick")),
    ]),
    ("kaiser", [
        _reg(Ability("kaiser_p1", "kaiser", "passive", 1, "Emperor",
            "+1 on his dribble, +2 on his shot. Everyone he shots past takes -1 "
            "until the next goal, and a goal pays him +2.",
            att=lambda c: 1 if c["action"] == "dribble" else (2 if c["action"] == "shoot" else 0),
            when=lambda c: c["action"] in ("dribble", "shoot"),
            beats=-1, through=3, goal_self=2)),
        _reg(Ability("kaiser_s1", "kaiser", "skill", 1, "Emperor's Draw",
            "Lost field duel → his team wins the set piece.",
            on_lost="foul")),
        _reg(Ability("kaiser_p2", "kaiser", "passive", 2, "Magnus Deuce",
            "+2 — sends the keeper the wrong way.",
            pen_edge=2)),
        _reg(Ability("kaiser_s2", "kaiser", "skill", 3, "Der Übermensch",
            "Shot scores even if the keeper is within 1 of his total.",
            save_margin=1, when=lambda c: c["action"] == "shoot")),
    ]),
    ("nagi", [
        _reg(Ability("nagi_p1", "nagi", "passive", 1, "Ultra Trap",
            "+2 Dribble straight off a received pass.",
            att=lambda c: 2 if c["action"] == "dribble" and _after_pass(c) else 0)),
        _reg(Ability("nagi_s1", "nagi", "skill", 1, "Impossible Trap",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("nagi_p2", "nagi", "passive", 2, "Lazy Genius",
            "+2 Shot when unmarked.",
            att=lambda c: 2 if c["action"] == "shoot" and _unmarked(c) else 0)),
        _reg(Ability("nagi_s2", "nagi", "skill", 3, "Cocoon Rebound",
            "First tackle against him fails: keeps the ball and gains a zone.",
            tackle_keep=True)),
    ]),
    ("shidou", [
        _reg(Ability("shidou_p1", "shidou", "passive", 1, "Box Predator",
            "+2 Shot from the Final Third onward.",
            att=lambda c: 2 if c["action"] == "shoot" and _final(c) else 0)),
        _reg(Ability("shidou_s1", "shidou", "skill", 1, "Chaos Rebound",
            "A punched shot rebounds straight back to him.",
            save_self=True)),
        _reg(Ability("shidou_p2", "shidou", "passive", 2, "Heating Up",
            "+1 Shot per goal already scored (max +3).",
            att=lambda c: min(3, c["self_goals"]))),
        _reg(Ability("shidou_s2", "shidou", "skill", 3, "Devil's Pulse",
            "Keeper −2 against his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot")),
    ]),
    # ---------------------------------------------------------------- SR
    ("barou", [
        _reg(Ability("barou_p1", "barou", "passive", 1, "Hungry G Point",
            "+2 Shot right after receiving a pass; +1 more if it goes in.",
            att=lambda c: 2 if c["action"] == "shoot" and _after_pass(c) else 0,
            goal_self=1)),
        _reg(Ability("barou_s1", "barou", "skill", 1, "Predator Tackle",
            "While marking: wins the ball with no roll.",
            auto="stop")),
        _reg(Ability("barou_p2", "barou", "passive", 2, "Villain's Revenge",
            "+2 Shot while trailing.",
            att=lambda c: 2 if c["action"] == "shoot" and _losing(c) else 0)),
        _reg(Ability("barou_s2", "barou", "skill", 3, "Tyrant's Run",
            "Beats his marker with no roll and gains an extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
    ]),
    ("chigiri", [
        _reg(Ability("chigiri_p1", "chigiri", "passive", 1, "Full Sprint",
            "+2 Dribble from Midfield.",
            att=lambda c: 2 if c["action"] == "dribble" and _mid(c) else 0)),
        _reg(Ability("chigiri_s1", "chigiri", "skill", 1, "Red Flash Breakaway",
            "Beats the back line with no roll + one extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("chigiri_p2", "chigiri", "passive", 2, "Second Gear",
            "+1 Dribble per defender beaten this attack (max +3).",
            att=lambda c: min(3, c["beaten_n"]) if c["action"] == "dribble" else 0)),
        _reg(Ability("chigiri_s2", "chigiri", "skill", 3, "Recovery Line",
            "Gamble: beats that many defenders with no roll (min 2). Low roll: ball lost.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble")),
    ]),
    ("bachira", [
        _reg(Ability("bachira_p1", "bachira", "passive", 1, "Monster Moment",
            "+2 on his dribble; +2 more if a goal follows.",
            att=lambda c: 2 if c["action"] == "dribble" else 0,
            goal_self=2)),
        _reg(Ability("bachira_s1", "bachira", "skill", 1, "Monster Time",
            "Beats his marker with no roll + one extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("bachira_p2", "bachira", "passive", 2, "Monster Freestyle",
            "Dice never roll below 2.",
            die_floor=2)),
        _reg(Ability("bachira_s2", "bachira", "skill", 3, "Golden Link",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2)),
    ]),
    ("reo", [
        _reg(Ability("reo_p1", "reo", "passive", 1, "Chameleon Copy",
            "+1 to all duels against an SSR opponent.",
            att=lambda c: 1 if _foe_rarity("SSR")(c) else 0)),
        _reg(Ability("reo_s1", "reo", "skill", 1, "Perfect Mimicry",
            "Gamble: 3+ beats the marker with no roll. 1–2: possession lost.",
            gamble=True, gamble_min=3, when=lambda c: True)),
        _reg(Ability("reo_p2", "reo", "passive", 2, "All-Round Rise",
            "+1 to all duels, always.",
            att=lambda c: 1)),
        _reg(Ability("reo_s2", "reo", "skill", 3, "Twin Engines",
            "+3 on his current action while Nagi is on his team.",
            att=lambda c: 3 if _mate("nagi")(c) else 0)),
    ]),
    ("hiori", [
        _reg(Ability("hiori_p1", "hiori", "passive", 1, "Silent Service",
            "Completed passes give the receiver +1 next action.",
            pass_buff=1)),
        _reg(Ability("hiori_s1", "hiori", "skill", 1, "Log-Out Ball",
            "Pass can't be intercepted; the receiver gains one zone.",
            pass_advance=1, when=lambda c: c["action"] == "pass")),
        _reg(Ability("hiori_p2", "hiori", "passive", 2, "Reading Room",
            "+1 Meta Vision defense while marking.",
            dfd=lambda c: 1)),
        _reg(Ability("hiori_s2", "hiori", "skill", 3, "Draw the Foul",
            "Lost field duel → his team wins the set piece.",
            on_lost="foul")),
    ]),
    ("otoya", [
        _reg(Ability("otoya_p1", "otoya", "passive", 1, "Ninja Gap",
            "+2 Shot when unmarked.",
            att=lambda c: 2 if c["action"] == "shoot" and _unmarked(c) else 0)),
        _reg(Ability("otoya_s1", "otoya", "skill", 1, "Backstab",
            "Intercepts a pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("otoya_p2", "otoya", "passive", 2, "First Strike",
            "+2 on his first duel of each attack.",
            att=lambda c: 2 if _first_link(c) else 0)),
        _reg(Ability("otoya_s2", "otoya", "skill", 3, "Shadow Step",
            "Gamble: beats that many unmarked runners with no roll (min 1); dribbles and runs.",
            gamble=True, when=lambda c: c["action"] == "dribble")),
    ]),
    ("karasu", [
        _reg(Ability("karasu_p1", "karasu", "passive", 1, "Crow's Read",
            "+1 Meta Vision defense while marking.",
            dfd=lambda c: 1)),
        _reg(Ability("karasu_s1", "karasu", "skill", 1, "Kill the Pass Lane",
            "Intercepts a pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("karasu_p2", "karasu", "passive", 2, "Game Management",
            "+1 attack and +1 defense while trailing.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("karasu_s2", "karasu", "skill", 3, "Checkmate Call",
            "His penalty always sends the keeper the wrong way.",
            pen_autoscore=True)),
    ]),
    ("yukimiya", [
        _reg(Ability("yukimiya_p1", "yukimiya", "passive", 1, "Orbital Shift",
            "+2 Dribble in the Final Third.",
            att=lambda c: 2 if c["action"] == "dribble" and c["zone"] == ZONE_SHOOT else 0)),
        _reg(Ability("yukimiya_s1", "yukimiya", "skill", 1, "Blind Speed Burst",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("yukimiya_p2", "yukimiya", "passive", 2, "F-Sequence",
            "Dice never roll below 2.",
            die_floor=2)),
        _reg(Ability("yukimiya_s2", "yukimiya", "skill", 3, "Knight's Blade",
            "Shot cuts through the marker; keeper −2.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=2,
            when=lambda c: c["action"] == "shoot")),
    ]),
    ("kunigami", [
        _reg(Ability("kunigami_p1", "kunigami", "passive", 1, "Long Shot",
            "+3 on his shot; +1 more if it goes in. Carries past one more defender.",
            att=lambda c: 3 if c["action"] == "shoot" else 0,
            through=2, goal_self=1)),
        _reg(Ability("kunigami_s1", "kunigami", "skill", 1, "Wild Card Volley",
            "Next action of any teammate +2; his own shot +1.",
            pass_buff=2, att=lambda c: 1 if c["action"] == "shoot" else 0)),
        _reg(Ability("kunigami_p2", "kunigami", "passive", 2, "Never Back Down",
            "+2 Shot while trailing.",
            att=lambda c: 2 if c["action"] == "shoot" and _losing(c) else 0)),
        _reg(Ability("kunigami_s2", "kunigami", "skill", 3, "Captain's Wall",
            "While behind: +2 on his shot, keeper −2.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=2,
            when=lambda c: c["action"] == "shoot" and _losing(c))),
    ]),
    # ---------------------------------------------------------------- R
    ("aryu", [
        _reg(Ability("aryu_p1", "aryu", "passive", 1, "Elegant Reach",
            "+1 defense against dribbles.",
            dfd=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("aryu_s1", "aryu", "skill", 1, "Aesthetic Block",
            "Blocks the opponent with no roll.",
            auto="stop")),
        _reg(Ability("aryu_p2", "aryu", "passive", 2, "Model Frame",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("aryu_s2", "aryu", "skill", 3, "Aesthetic Aria",
            "Direct free kick: ties go his way.",
            att=lambda c: 1 if c["action"] == "freekick" else 0, tie_win=True,
            when=lambda c: c["action"] == "freekick")),
    ]),
    ("gagamaru", [
        _reg(Ability("gagamaru_p1", "gagamaru", "passive", 1, "Instinct Guard",
            "Team keeper plays +1 while he's on the pitch.",
            aura_gk=1)),
        _reg(Ability("gagamaru_s1", "gagamaru", "skill", 1, "Beast Reflex",
            "Shuts down an opponent with no roll.",
            auto="stop")),
        _reg(Ability("gagamaru_p2", "gagamaru", "passive", 2, "Acrobatic Clearance",
            "+1 Meta Vision defense while marking.",
            dfd=lambda c: 1)),
        _reg(Ability("gagamaru_s2", "gagamaru", "skill", 3, "Last Line Claim",
            "Claims his keeper's punched ball for his team.",
            punch_to_self=True)),
    ]),
    ("raichi", [
        _reg(Ability("raichi_p1", "raichi", "passive", 1, "Mad Dog Press",
            "+1 defense against dribblers.",
            dfd=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("raichi_s1", "raichi", "skill", 1, "Rage Tackle",
            "Wins the ball outright with no roll.",
            auto="stop")),
        _reg(Ability("raichi_p2", "raichi", "passive", 2, "Momentum Fury",
            "+1 defense per stop this match (max +3).",
            dfd=lambda c: min(3, c["self_stops"]))),
        _reg(Ability("raichi_s2", "raichi", "skill", 3, "Warrior's Grit",
            "Lost field duel → he wins the free kick instead.",
            on_lost="foul")),
    ]),
    ("iemon", [
        _reg(Ability("iemon_p1", "iemon", "passive", 1, "Anchor Presence",
            "+1 Passing from Midfield.",
            att=lambda c: 1 if c["action"] == "pass" and _mid(c) else 0)),
        _reg(Ability("iemon_s1", "iemon", "skill", 1, "Set-Piece Script",
            "On his set piece: keeper reads the wrong corner on penalties; ties go his way on free kicks.",
            tie_win=True, pen_edge=2)),
        _reg(Ability("iemon_p2", "iemon", "passive", 2, "Cool Head",
            "+1 attack and +1 defense while the score is level.",
            att=lambda c: 1 if _level(c) else 0,
            dfd=lambda c: 1 if _level(c) else 0)),
        _reg(Ability("iemon_s2", "iemon", "skill", 3, "Game Script",
            "Gamble: 3+ pass or dribble beats the marker with no roll. 1–2: possession lost.",
            gamble=True, gamble_min=3, when=lambda c: c["action"] in ("pass", "dribble"))),
    ]),
    ("naruhaya", [
        _reg(Ability("naruhaya_p1", "naruhaya", "passive", 1, "Feint Master",
            "+2 Dribble on the first duel of each attack.",
            att=lambda c: 2 if c["action"] == "dribble" and _first_link(c) else 0)),
        _reg(Ability("naruhaya_s1", "naruhaya", "skill", 1, "Scam Step",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("naruhaya_p2", "naruhaya", "passive", 2, "Tireless Engine",
            "+1 Dribble after halftime.",
            att=lambda c: 1 if c["action"] == "dribble" and c["turn"] * 2 > c["limit"] else 0)),
        _reg(Ability("naruhaya_s2", "naruhaya", "skill", 3, "Grand Scam",
            "Gamble: 4+ beats that many defenders with no roll; 1–3 loses the duel.",
            gamble=True, gamble_min=4, when=lambda c: c["action"] == "dribble")),
    ]),
    ("kurona", [
        _reg(Ability("kurona_p1", "kurona", "passive", 1, "Shark Instinct",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("kurona_s1", "kurona", "skill", 1, "Run Through",
            "Beats his marker with no roll + one extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("kurona_p2", "kurona", "passive", 2, "One-Touch Shot",
            "+2 Shot right after receiving a pass.",
            att=lambda c: 2 if c["action"] == "shoot" and _after_pass(c) else 0)),
        _reg(Ability("kurona_s2", "kurona", "skill", 3, "Piranha Press",
            "Strips the ball carrier with no roll.",
            auto="stop", when=lambda c: c["action"] == "dribble")),
    ]),
    ("tokimitsu", [
        _reg(Ability("tokimitsu_p1", "tokimitsu", "passive", 1, "Anxiety Surge",
            "+2 to all duels while losing.",
            att=lambda c: 2 if _losing(c) else 0)),
        _reg(Ability("tokimitsu_s1", "tokimitsu", "skill", 1, "Muscle Shield",
            "Shrugs off his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("tokimitsu_p2", "tokimitsu", "passive", 2, "Iron Body",
            "+1 Meta Vision defense while marking.",
            dfd=lambda c: 1)),
        _reg(Ability("tokimitsu_s2", "tokimitsu", "skill", 3, "Explosive Drive",
            "Beats his marker with no roll + two extra zones.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
    ]),
    # ---------------------------------------------------------------- N
    ("wanima_a", [
        _reg(Ability("wanima_a_p1", "wanima_a", "passive", 1, "Twin Sync",
            "+1 to all duels while his twin is on his team.",
            att=lambda c: 1 if _mate("wanima_j")(c) else 0)),
        _reg(Ability("wanima_a_s1", "wanima_a", "skill", 1, "Overlap Run",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("wanima_a_p2", "wanima_a", "passive", 2, "Chemistry",
            "+2 Passing while his twin is on the pitch.",
            att=lambda c: 2 if c["action"] == "pass" and _mate("wanima_j")(c) else 0)),
        _reg(Ability("wanima_a_s2", "wanima_a", "skill", 3, "Twin Magic",
            "On his pass, exact ties go his way.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("wanima_j", [
        _reg(Ability("wanima_j_p1", "wanima_j", "passive", 1, "Twin Sync",
            "+1 to all duels while his twin is on his team.",
            att=lambda c: 1 if _mate("wanima_a")(c) else 0)),
        _reg(Ability("wanima_j_s1", "wanima_j", "skill", 1, "Overlap Run",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("wanima_j_p2", "wanima_j", "passive", 2, "Chemistry",
            "+2 Passing while his twin is on the pitch.",
            att=lambda c: 2 if c["action"] == "pass" and _mate("wanima_a")(c) else 0)),
        _reg(Ability("wanima_j_s2", "wanima_j", "skill", 3, "Twin Magic",
            "On his pass, exact ties go his way.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("igaguri", [
        _reg(Ability("igaguri_p1", "igaguri", "passive", 1, "Tryhard Heart",
            "Dice never roll below 2.",
            die_floor=2)),
        _reg(Ability("igaguri_s1", "igaguri", "skill", 1, "Miracle Hustle",
            "Beats the marker with no roll on any action.",
            auto="win")),
        _reg(Ability("igaguri_p2", "igaguri", "passive", 2, "Grind Mode",
            "+1 to all duels while losing.",
            att=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("igaguri_s2", "igaguri", "skill", 3, "Destiny Shove",
            "Lost field duel → the foul is called his way.",
            on_lost="foul")),
    ]),
    ("hyoma_k", [
        _reg(Ability("hyoma_k_p1", "hyoma_k", "passive", 1, "Selfless Lane",
            "+2 Passing from Midfield.",
            att=lambda c: 2 if c["action"] == "pass" and _mid(c) else 0)),
        _reg(Ability("hyoma_k_s1", "hyoma_k", "skill", 1, "Decoy Run",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2)),
        _reg(Ability("hyoma_k_p2", "hyoma_k", "passive", 2, "Workhorse",
            "+1 attack and +1 defense while trailing.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("hyoma_k_s2", "hyoma_k", "skill", 3, "Killer Key",
            "Completed pass: exact ties go his way — never cut out on the level.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("yuki", [
        _reg(Ability("yuki_p1", "yuki", "passive", 1, "Quiet Focus",
            "+1 defense against passes.",
            dfd=lambda c: 1 if c["action"] == "pass" else 0)),
        _reg(Ability("yuki_s1", "yuki", "skill", 1, "Ice Vein",
            "While level: dice never roll below 4 this attack.",
            die_floor=4, when=lambda c: _level(c))),
        _reg(Ability("yuki_p2", "yuki", "passive", 2, "Unshakeable",
            "Dice never roll below 2.",
            die_floor=2)),
        _reg(Ability("yuki_s2", "yuki", "skill", 3, "Clutch Minute",
            "While level or within one goal: shot ignores the keeper's die.",
            att=lambda c: 2 if abs(c["diff"]) <= 1 else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and abs(c["diff"]) <= 1)),
    ]),
    ("kira", [
        _reg(Ability("kira_p1", "kira", "passive", 1, "Fallen Ace",
            "+2 Shot from the Final Third onward.",
            att=lambda c: 2 if c["action"] == "shoot" and _final(c) else 0)),
        _reg(Ability("kira_s1", "kira", "skill", 1, "Redemption Strike",
            "While trailing: shot +3; level or ahead: shot +1 and keeper −1.",
            att=lambda c: 3 if c["action"] == "shoot" and _losing(c) else 1 if c["action"] == "shoot" else 0,
            gk_down=1,
            when=lambda c: c["action"] == "shoot")),
        _reg(Ability("kira_p2", "kira", "passive", 2, "Chip on Shoulder",
            "+1 to all duels against an SSR opponent.",
            att=lambda c: 1 if _foe_rarity("SSR")(c) else 0)),
        _reg(Ability("kira_s2", "kira", "skill", 3, "Star Reborn",
            "+1 Shot and keeper −2.",
            att=lambda c: 1 if c["action"] == "shoot" else 0, gk_down=2)),
    ]),
]

for char_key, items in _KITS:
    # starters = passives only — skills start LOCKED and are bought later
    STARTERS[char_key] = [ab.id for ab in items if ab.tier == 1 and ab.kind == "passive"]
    BY_CHAR[char_key] = items

from .abilities_extra import register_extras as _register_extras

_register_extras()

from .abilities_roster import register_extras as _register_roster

_register_roster()

from .abilities_bound import register_extras as _register_bound
_register_bound()


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
