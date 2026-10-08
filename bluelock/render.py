"""Duel outcome text — pure render functions (moved out of engine)."""

import random
from .config import KEEPER_NAME

def duel_line(out: dict) -> str:
    if out["defender"] is None and not out.get("wall_rolls"):
        return ""
    att_boosts = out.get("att_boosts") or []
    def_boosts = out.get("def_boosts") or []
    att_parts = [f"{out['att_die']}"] + [f"⚡{n}" for _, n in att_boosts]
    att_sum = "+".join(att_parts) + f"+{out['att_power']}"
    att_total = f"{out['att_total']}" if out["att_total"] is not None else "?"
    if out.get("wall_rolls"):
        return f"<code>{att_sum}={att_total}</code> vs 🧱 <i>wall</i>"
    if out.get("def_die") is None:
        if out.get("att_die") is None:
            return ""
        return f"<code>{att_sum}={att_total}</code>"
    def_parts = [f"{out['def_die']}"] + [f"🛡{n}" for _, n in def_boosts]
    def_sum = "+".join(def_parts) + f"+{out['def_power']}"
    def_total = f"{out['def_total']}" if out["def_total"] is not None else "?"
    return (
        f"<code>{att_sum}={att_total}</code> vs "
        f"<code>{def_sum}={def_total}</code>"
    )


def wall_line(out: dict, by_slot: dict) -> str:
    rolls = out.get("wall_rolls") or []
    if not rolls:
        return ""
    rows = []
    for r in rolls:
        row = by_slot.get(r["slot"])
        if row is None:
            continue
        mark = "💨" if r["slot"] in (out.get("beaten") or []) else "🛡"
        rows.append(
            f"   {mark} <b>{row['name']}</b> <code>{r['die']}+{out['def_power']}</code>"
        )
    return "\n".join(rows)


def gk_line(out: dict) -> str:
    if out["gk_die"] is None:
        return ""
    eff = out.get("gk_total_eff")
    shown = eff if eff is not None else out["gk_total"]
    return (
        f"<code>{out['att_die']}+{out['att_power']}={out['att_total']}</code> vs "
        f"🧤<code>{out['gk_die']}+{out['gk_power']}={shown}</code>"
    )



# ------------------------------------------------------- Phase 7: commentary pools
# Base lines per outcome — describe() picks one at random so matches never read
# the same twice. Only the plain branches are swapped; skill/walk/gamble specials
# and every follow-up line (assist, nerve, wall, gk) stay deterministic.
COMMENTARY: dict[str, tuple[str, ...]] = {
    "goal": (
        f"⚽️ <b>GOAL — {{actor}}</b> beats {KEEPER_NAME}!",
        f"⚽️ <b>GOAL!</b> <b>{{actor}}</b> buries it — {KEEPER_NAME} never moved!",
        f"⚽️ <b>GOAL — {{actor}}</b> with ice in his veins! {KEEPER_NAME} beaten!",
        f"⚽️ <b>GOAL!</b> <b>{{actor}}</b> unleashes — and the net bulges past {KEEPER_NAME}!",
    ),
    "pass_ok": (
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — a sharp pass into the channel",
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — threaded through the line",
        "🎯 <b>{actor}</b> ➜ <b>{target}</b> — the delivery finds its mark",
    ),
    "dribble_ok": (
        "🌀 <b>{actor}</b> dribbles past <b>{defender}</b> — he's out of the play.",
        "🌀 <b>{defender}</b> buys the feint — <b>{actor}</b> is gone.",
        "🌀 <b>{actor}</b> twists away from <b>{defender}</b> — nothing but his back.",
    ),
    "tackled": (
        "🦵 <b>{defender}</b> takes the ball off <b>{actor}</b>.",
        "🦵 <b>{defender}</b> times it perfectly — <b>{actor}</b> loses it.",
        "🦵 clean challenge — <b>{defender}</b> rips it off <b>{actor}</b>.",
    ),
    "intercepted": (
        "🚫 <b>{defender}</b> reads <b>{actor}</b>'s delivery.",
        "🚫 <b>{defender}</b> cuts it out — <b>{actor}</b>'s ball never arrives.",
        "🚫 <b>{defender}</b> sees it coming and steps in front of <b>{actor}</b>.",
    ),
    "saved": (
        f"🧤 <b>{KEEPER_NAME}</b> denies <b>{{actor}}</b> —",
        f"🧤 <b>{KEEPER_NAME}</b> shuts the door on <b>{{actor}}</b> —",
        f"🧤 huge hands — <b>{KEEPER_NAME}</b> answers <b>{{actor}}</b> —",
    ),
    "blocked": (
        "🧱 <b>{defender}</b> blocks <b>{actor}</b>'s effort.",
        "🧱 <b>{defender}</b> throws himself in — <b>{actor}</b>'s path is closed.",
        "🧱 brave defending — <b>{defender}</b> shuts <b>{actor}</b> down.",
    ),
    "wall": (
        f"🧱 <b>{{actor}}</b>'s effort is swarmed — the wall holds.",
        f"🧱 the wall stands tall — <b>{{actor}}</b>'s shot crashes off it.",
        f"🧱 bodies everywhere — <b>{{actor}}</b> can't punch through.",
    ),
}


def commentary(key: str, **kw) -> str:
    """Pick one random base line from a COMMENTARY pool and render it."""
    return random.choice(COMMENTARY[key]).format(**kw)


def big_moment_lines(out: dict, goals: int) -> list[str]:
    """Extra hype lines for a goal — hat-trick, gamble payoff.

    Quiet goals return nothing: every added line must earn its place.
    """
    notes: list[str] = []
    if goals >= 3:
        notes.append("🎩 <b>HAT-TRICK!</b>")
    if out.get("gamble_beaten"):
        notes.append(f"🎲 <b>RISK PAID OFF</b> — {out['gamble_beaten']} beaten on the die.")
    return notes


def describe(out: dict, by_slot: dict | None = None) -> str:
    actor = out["actor"]["name"]
    outcome = out["outcome"]
    duel = duel_line(out)
    wall_txt = wall_line(out, by_slot or {})
    defender = out["defender"]["name"] if out["defender"] else "—"
    free = " <i>(unmarked — everyone's beaten)</i>" if out.get("unmarked") else ""

    if outcome == "pass_ok":
        if out.get("walked"):
            line = f"🎯 <b>{actor}</b> ➜ <b>{out['target']['name']}</b> — a casual ball into open space. <i>No duel needed.</i>"
        else:
            line = commentary("pass_ok", actor=actor, target=out["target"]["name"]) + f".{free} {duel}"
        if out.get("pass_advanced"):
            line += "\n     ➡️ the cut-back carries the play a zone forward"
        return line
    if outcome == "cross_ok":
        return (
            f"📢 <b>{actor}</b> swings the free kick into <b>{out['target']['name']}</b> — "
            f"delivery arrived.{free} {duel}"
        )
    if outcome == "intercepted":
        line = commentary("intercepted", actor=actor, defender=defender) + f" {duel}"
        if out.get("stopped_by_skill"):
            line = f"🚫 <b>{out['stopped_by_skill']['name']}</b> snuffs out <b>{actor}</b>'s play before it begins."
        if out.get("first_free"):
            line += "\n     🔁 <b>…but the loss doesn't count.</b> <i>One more try.</i>"
        return line
    if outcome == "dribble_ok":
        if out.get("stopped_by_skill"):
            return f"🌀 <b>{actor}</b> leaves <b>{defender}</b> grasping at air — gone."
        if out.get("gamble_beaten"):
            return (
                f"🎲 <b>{actor}</b> rolls the dice and ghosts past <b>{defender}</b> —"
                f" <b>{out['gamble_beaten']}</b> defenders beaten without a fight.{free}"
            )
        if out["defender"] is None:
            if out.get("walked"):
                return f"🚶 <b>{actor}</b> advances unopposed — the road ahead is clear.{free}"
            return f"🌀 <b>{actor}</b> drives forward — no one left to stop him.{free}"
        return commentary("dribble_ok", actor=actor, defender=defender) + f" {duel}"
    if outcome == "tackled":
        if out.get("stopped_by_skill"):
            return f"🦵 <b>{out['stopped_by_skill']['name']}</b> wins the ball off <b>{actor}</b> outright."
        return commentary("tackled", actor=actor, defender=defender) + f" {duel}"
    if outcome == "blocked":
        if out.get("gamble_backfire"):
            return f"💀 <b>{actor}</b>'s gamble collapses — <b>{defender}</b> was ready for it all along."
        if out.get("stopped_by_skill"):
            return f"🧱 <b>{out['stopped_by_skill']['name']}</b> throws himself in front of <b>{actor}</b>'s effort."
        line = commentary("blocked", actor=actor, defender=defender) + f" {duel}"
        if out["action"] == "shoot":
            line = commentary("wall", actor=actor) + f" {duel}"
            if wall_txt:
                line = commentary("wall", actor=actor)
                line += "\n" + wall_txt
        if out.get("first_free"):
            line += "\n     🔁 <b>…but the loss doesn't count.</b> <i>One more try.</i>"
        return line
    if outcome == "goal":
        line = commentary("goal", actor=actor)
        if out["action"] == "penalty":
            line += f"\n     🎯 <b>{out['att_spot']}</b> in — keeper dived {out['gk_spot']}"
            return line
        if out["action"] == "shoot" and wall_txt:
            line += "\n     🧱 every defender beaten:"
            line += "\n" + wall_txt
        elif duel:
            line += f"\n     🛡 {duel}"
        elif out["action"] == "freekick":
            line += "\n     🎯 straight off the dead ball"
        else:
            line += "\n     🛡 no marker left — free shot"
        line += f"\n     🧤 {gk_line(out)}"
        if out.get("assister"):
            line += f"\n     🅰 Assist — <b>{out['assister']['name']}</b>"
        return line
    if outcome == "saved":
        catch = out.get("keeper_dist") == "catch"
        head = "holds it 🧤" if catch else "punches it away 💥"
        line = commentary("saved", actor=actor) + f" {head}"
        if out["action"] == "penalty":
            if out.get("erased"):
                line += "\n     ⛔ no guess was needed — the chance is erased"
                return line
            line += f"\n     🎯 shot {out['att_spot']} — keeper read it"
            return line
        if out["action"] == "shoot" and wall_txt:
            line += "\n     🧱 the whole wall was brushed aside:"
            line += "\n" + wall_txt
        elif duel:
            line += f"\n     🛡 {duel}"
        line += f"\n     🧤 {gk_line(out)}"
        if not catch:
            line += f"\n     ➜ loose ball falls to <b>{out['receiver']['name']}</b>"
        return line
    if outcome == "foul":
        piece = "PENALTY 🥶" if out["set_piece"] == "penalty" else "FREE KICK 🎯"
        reason = out.get("reason")
        if reason == "drawn":
            return f"🎭 <b>{actor}</b> wins the referee's whistle — <b>{piece}</b>! {duel}"
        if wall_txt:
            base = f"⚖️ Deadlock — <b>{piece}</b> for <b>{actor}</b>. {duel}"
            base += "\n" + wall_txt
            return base
        return f"⚖️ Deadlock — <b>{piece}</b> for <b>{actor}</b>. {duel}"
    return duel
