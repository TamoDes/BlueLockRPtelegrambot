from . import db, economy
from .config import (
    ASSIST_VALUE,
    DRAW_VALUE,
    FRIENDLY_RATE,
    FRIENDLY_XP_RATE,
    GOAL_TARGET,
    GOAL_VALUE,
    LEVEL_UP_BONUS,
    MOTM_VALUE,
    PLAY_VALUE,
    RECAP_KEEP,
    WIN_VALUE,
    XP_ACTION,
    XP_ASSIST,
    XP_DRAW,
    XP_GOAL,
    XP_LOSS,
    XP_STOP,
    XP_WIN,
    level_for,
)
from .fmt import HEAVY, RULE, clip, esc, yen_short


def settle(match_id: int) -> tuple[str, list[tuple[int, int, int]]] | None:
    with db.tx() as c:
        cur = c.execute(
            "UPDATE matches SET status='done', phase='done', ended_at=? WHERE id=? AND status='live'",
            (db.now(), match_id),
        )
        if cur.rowcount != 1:
            return None

    match = db.match(match_id)
    roster = db.roster(match_id)
    friendly = match["mode"] == "friendly"
    rate = FRIENDLY_RATE if friendly else 1.0
    xp_rate = FRIENDLY_XP_RATE if friendly else 1.0
    s1, s2 = match["score1"], match["score2"]

    level_ups = []
    enriched = []
    for r in roster:
        mine, theirs = (s1, s2) if r["team"] == 1 else (s2, s1)
        base_payout = PLAY_VALUE + r["goals"] * GOAL_VALUE + r["assists"] * ASSIST_VALUE
        gained_xp = (
            XP_ACTION * r["actions"]
            + XP_GOAL * r["goals"]
            + XP_ASSIST * r["assists"]
            + XP_STOP * r["stops"]
        )

        if mine > theirs:
            base_payout += WIN_VALUE
            gained_xp += XP_WIN
        elif mine == theirs:
            base_payout += DRAW_VALUE
            gained_xp += XP_DRAW
        else:
            gained_xp += XP_LOSS

        payout = int(base_payout * rate)
        xp_gain = int(gained_xp * xp_rate)
        motm_score = r["goals"] * 3 + r["assists"] * 2 + r["stops"]
        enriched.append((r, payout, xp_gain, motm_score))

    top = max((e[3] for e in enriched), default=0)
    motm_row = next((e for e in enriched if e[3] == top and top > 0), None)

    for r, payout, gained_xp, score in enriched:
        is_motm = motm_row is not None and r["slot"] == motm_row[0]["slot"]
        bonus = MOTM_VALUE if is_motm else 0

        before = db.player(r["user_id"])
        old_level = level_for(before["xp"]) if before else 1
        db.add_xp(r["user_id"], gained_xp)
        new_level = level_for(db.player(r["user_id"])["xp"])
        if new_level > old_level:
            payout += LEVEL_UP_BONUS * (new_level - old_level)
            level_ups.append((r["user_id"], old_level, new_level))
        db.add_yen(r["user_id"], payout + bonus, f"match #{match_id}")

    new_medals = []
    for r in roster:
        if r["user_id"] is None:
            continue
        for medal in economy.check_and_grant(r["user_id"]):
            new_medals.append((r["name"], medal))

    if s1 == s2:
        verdict = "🤝 <b>Draw</b> — honours even."
    else:
        winner = "🔵 <b>Blue</b>" if s1 > s2 else "🔴 <b>Red</b>"
        verdict = f"🏆 {winner} wins <b>{s1}—{s2}</b>"
        if max(s1, s2) >= GOAL_TARGET and not friendly:
            verdict += f"\n🥇 Hit {GOAL_TARGET} first."

    lines = []
    for r, payout, gained_xp, score in enriched:
        is_motm = motm_row is not None and r["slot"] == motm_row[0]["slot"]
        total_in = payout + (MOTM_VALUE if is_motm else 0)
        detail = []
        if r["goals"]:
            detail.append(f"{r['goals']} goal{'s' if r['goals'] > 1 else ''}")
        if r["assists"]:
            detail.append(f"{r['assists']} assist{'s' if r['assists'] > 1 else ''}")
        if r["stops"]:
            detail.append(f"{r['stops']} stop{'s' if r['stops'] > 1 else ''}")
        row_text = (
            f"{'🌟 ' if is_motm else ''}<b>{esc(r['name'][:16])}</b>"
            f" · +{yen_short(total_in)} · +{gained_xp}xp"
        )
        if detail:
            row_text += f"\n   <i>{', '.join(detail)}</i>"
        lines.append(row_text)

    report = (
        f"🏁 <b>FULL TIME · #{match_id}</b>\n"
        f"{verdict}\n{HEAVY}\n"
        f"💸 <b>Payouts</b>\n"
        + "\n".join(lines)
    )
    recap = [clip(line.splitlines()[0], 44) for line in db.recent_events(match_id, RECAP_KEEP)]
    if recap:
        report += f"\n{RULE}\n📻 <b>Last plays</b>\n" + "\n".join(f"• {line}" for line in recap)
    if motm_row is not None:
        report += (
            f"\n{RULE}\n🌟 <b>MAN OF THE MATCH</b> — <b>{motm_row[0]['name']}</b> "
            f"(+{yen_short(MOTM_VALUE)} bonus)"
        )
    if level_ups:
        report += f"\n📈 Level-up bonus × {len(level_ups)}"
    if new_medals:
        report += "\n🏅 " + " · ".join(f"{esc(name)} earned {economy.medal_label(medal)}" for name, medal in new_medals[:6])
    if friendly:
        report += "\n<i>Friendly — 40%¥ · 60%xp applied.</i>"
    return report, level_ups


def settle_forced(match_id: int) -> tuple[str, list] | None:
    match = db.match(match_id)
    if not match:
        return None
    with db.tx() as c:
        c.execute(
            "UPDATE matches SET status='live', phase='play' WHERE id=? AND status='done'",
            (match_id,),
        )
    return settle(match_id)
