from dataclasses import dataclass
from typing import Callable, Optional

from . import db
from .config import (
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

PASSIVE_CHARGES = 2


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
    flavor: str
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
    aura_gk: int = 0
    gamble: bool = False
    gamble_min: int = 0
    long_shot: bool = False
    pass_advance: int = 0
    first_free: bool = False


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
        _reg(Ability("isagi_p1", "isagi", "passive", 1, "Direct Hit",
            "「I'll devour this play.」",
            "Passive: +2 Shot when shooting immediately after receiving a pass.",
            att=lambda c: 2 if c["action"] == "shoot" and _after_pass(c) else 0)),
        _reg(Ability("isagi_s1", "isagi", "skill", 1, "Meta Vision Read",
            "「The field is a puzzle — and I already solved it.」",
            "Once per match: while marking, he instantly reads an opponent pass and intercepts it without any dice.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("isagi_p2", "isagi", "passive", 2, "Devour the Stage",
            "「Your weapon is mine now.」",
            "Passive: the FIRST time he loses a field duel each match, the play devours itself — the loss doesn't count and he gets the ball back for one more try. (Arm it like any passive; it triggers automatically on the loss.)",
            first_free=True)),
        _reg(Ability("isagi_s2", "isagi", "skill", 3, "Checkmate Finish",
            "「Checkmate.」",
            "Once per match: his shot is scored even if the keeper matches it within 1 point of his total.",
            save_margin=1, when=lambda c: c["action"] == "shoot")),
    ]),
    ("rin", [
        _reg(Ability("rin_p1", "rin", "passive", 1, "Cold Predator",
            "「I don't need anyone. I'll destroy them alone.」",
            "Passive: +2 to ALL his duel powers while his team is losing — the ace wakes up when it matters.",
            att=lambda c: 2 if _losing(c) else 0)),
        _reg(Ability("rin_s1", "rin", "skill", 1, "Perfect Form",
            "「This is the ideal strike I've been building toward.」",
            "Once per match: when he shoots, he beats his marker automatically without rolling a single die.",
            auto="win", when=lambda c: c["action"] == "shoot")),
        _reg(Ability("rin_p2", "rin", "passive", 2, "Bloodline Rivalry",
            "「Brother… watch me surpass you.」",
            "Passive: +2 attack while Yoichi Isagi is on his team (their rivalry pushes him further), and +2 Meta Vision when facing Sae Itoshi across the pitch.",
            att=lambda c: 2 if _mate("isagi")(c) else 0,
            dfd=lambda c: 2 if _foe("sae")(c) else 0)),
        _reg(Ability("rin_s2", "rin", "skill", 3, "Itoshi Curl",
            "「Bend reality itself.」",
            "Once per match: +3 Free Kick power, and ties on his direct free kicks now go HIS way instead of the wall's.",
            att=lambda c: 3 if c["action"] == "freekick" else 0,
            tie_win=True, when=lambda c: c["action"] == "freekick")),
    ]),
    ("sae", [
        _reg(Ability("sae_p1", "sae", "passive", 1, "World-Class Weight",
            "「A pass with the right weight changes everything.」",
            "Passive: +2 Passing power — defenders struggle to cut out his perfectly weighted balls.",
            att=lambda c: 2 if c["action"] == "pass" else 0)),
        _reg(Ability("sae_s1", "sae", "skill", 1, "Maestro's Through Ball",
            "「Run. I'll put it exactly where you dream of it.」",
            "Once per match: his next completed pass grants the receiver +2 on their following action.",
            pass_buff=2)),
        _reg(Ability("sae_p2", "sae", "passive", 2, "Possession Metronome",
            "「Tempo is a weapon.」",
            "Passive: +1 to all his duel powers whenever his team holds possession parity or better (not trailing).",
            att=lambda c: 1 if not _losing(c) else 0)),
        _reg(Ability("sae_s2", "sae", "passive", 3, "Genius Arc",
            "「Talent like mine bends games around it.」",
            "Passive: +2 Free Kick power, and his penalty nerve checks gain +2 — pure technique beats panic.",
            att=lambda c: 2 if c["action"] == "freekick" else 0, pen_edge=2)),
    ]),
    ("kaiser", [
        _reg(Ability("kaiser_p1", "kaiser", "passive", 1, "Kaiser Impact",
            "「The ball flies where the Emperor wills it.」",
            "Passive: +2 Shot when shooting inside the box.",
            att=lambda c: 2 if c["action"] == "shoot" and _box(c) else 0)),
        _reg(Ability("kaiser_s1", "kaiser", "skill", 1, "Emperor's Draw",
            "「Touch me again and it's a card.」",
            "Once per match: when he loses a field duel, the referee buys the theatrics — his team wins the resulting set piece.",
            on_lost="foul")),
        _reg(Ability("kaiser_p2", "kaiser", "passive", 2, "Magnus Deuce",
            "「Twelve meters? That's my kingdom.」",
            "Passive: +2 on penalty nerve checks — ice in his veins from twelve yards.",
            pen_edge=2)),
        _reg(Ability("kaiser_s2", "kaiser", "skill", 3, "Der Übermensch",
            "「There is no keeper. Only delay.」",
            "Once per match: his shot scores even if the keeper matches it within 1 point of his total.",
            save_margin=1, when=lambda c: c["action"] == "shoot")),
    ]),
    ("nagi", [
        _reg(Ability("nagi_p1", "nagi", "passive", 1, "Ultra Trap",
            "「What a hassle… fine, one more.」",
            "Passive: +2 Dribble when dribbling straight off a received pass — his first touch kills any pressure.",
            att=lambda c: 2 if c["action"] == "dribble" and _after_pass(c) else 0)),
        _reg(Ability("nagi_s1", "nagi", "skill", 1, "Impossible Trap",
            "「That was kind of awesome, actually.」",
            "Once per match: glues an impossible first touch to the ball — beats his marker without rolling.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("nagi_p2", "nagi", "passive", 2, "Lazy Genius",
            "「If nobody's near me, why would I move?」",
            "Passive: +2 Shot when he finds space completely unmarked.",
            att=lambda c: 2 if c["action"] == "shoot" and _unmarked(c) else 0)),
        _reg(Ability("nagi_s2", "nagi", "skill", 3, "Cocoon Rebound",
            "「I'm not done being a genius yet.」",
            "Once per match: the first time he gets tackled, he rolls out of it — keeps the ball and still advances a zone.",
            tackle_keep=True)),
    ]),
    ("shidou", [
        _reg(Ability("shidou_p1", "shidou", "passive", 1, "Box Predator",
            "「Feed me and I'll score. Simple.」",
            "Passive: +2 Shot when attacking from the Final Third onward.",
            att=lambda c: 2 if c["action"] == "shoot" and _final(c) else 0)),
        _reg(Ability("shidou_s1", "shidou", "skill", 1, "Chaos Rebound",
            "「Miss? Me? That just means I shoot again.」",
            "Once per match: when his shot is punched away, the chaos lands the rebound straight back at his feet.",
            save_self=True)),
        _reg(Ability("shidou_p2", "shidou", "passive", 2, "Heating Up",
            "「Every goal makes me crazier.」",
            "Passive: +1 Shot for each goal he has already scored this match (max +3).",
            att=lambda c: min(3, c["self_goals"]))),
        _reg(Ability("shidou_s2", "shidou", "skill", 3, "Devil's Pulse",
            "「The goal screams my name.」",
            "Once per match: his shot strikes with such violence the keeper's effective power drops by 2.",
            gk_down=2, when=lambda c: c["action"] == "shoot")),
    ]),
    # ---------------------------------------------------------------- SR
    ("barou", [
        _reg(Ability("barou_p1", "barou", "passive", 1, "King's Domain",
            "「Kneel. The penalty area is mine.」",
            "Passive: +2 Shot inside the box.",
            att=lambda c: 2 if c["action"] == "shoot" and _box(c) else 0)),
        _reg(Ability("barou_s1", "barou", "skill", 1, "Predator Tackle",
            "「Steal it, then finish it myself.」",
            "Once per match: while marking, he rips the ball away with overwhelming force — no dice rolled.",
            auto="stop")),
        _reg(Ability("barou_p2", "barou", "passive", 2, "Villain's Revenge",
            "「You woke the wrong King.」",
            "Passive: +2 Shot while his team is trailing.",
            att=lambda c: 2 if c["action"] == "shoot" and _losing(c) else 0)),
        _reg(Ability("barou_s2", "barou", "skill", 3, "Tyrant's Run",
            "「Out of my way. All of you.」",
            "Once per match: steamrolls his marker without rolling AND plows an extra zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
    ]),
    ("chigiri", [
        _reg(Ability("chigiri_p1", "chigiri", "passive", 1, "Full Sprint",
            "「The moment the lane opens… I'm gone.」",
            "Passive: +2 Dribble when launching from Midfield.",
            att=lambda c: 2 if c["action"] == "dribble" and _mid(c) else 0)),
        _reg(Ability("chigiri_s1", "chigiri", "skill", 1, "Red Flash Breakaway",
            "「Fastest eleven seconds in Blue Lock.」",
            "Once per match: outpaces the entire back line without rolling and bursts an extra zone up the pitch.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("chigiri_p2", "chigiri", "passive", 2, "Second Gear",
            "「My legs haven't even warmed up.」",
            "Passive: +1 Dribble per defender already beaten this attack — the more he burns, the faster he gets (max +3).",
            att=lambda c: min(3, c["beaten_n"]) if c["action"] == "dribble" else 0)),
        _reg(Ability("chigiri_s2", "chigiri", "skill", 3, "Recovery Line",
            "「From our box to theirs — one run.」",
            "Gamble: roll the die — that's how many defenders he ghosts past without a fight (min 2), marker or no marker. Low roll and the legs give out: ball lost.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble")),
    ]),
    ("bachira", [
        _reg(Ability("bachira_p1", "bachira", "passive", 1, "Monster Dribble",
            "「Wanna see my monster?」",
            "Passive: +2 Dribble on the very first duel of an attack — the monster comes out to play early.",
            att=lambda c: 2 if c["action"] == "dribble" and _first_link(c) else 0)),
        _reg(Ability("bachira_s1", "bachira", "skill", 1, "Monster Time",
            "「It's showtime!」",
            "Once per match: hypnotic footwork beats his marker without rolling and carries him an extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("bachira_p2", "bachira", "passive", 2, "Freestyle Flow",
            "「Improvisation is my mother tongue.」",
            "Passive: his dice never show less than 2 — chaotic creativity rescues even bad rolls.",
            die_floor=2)),
        _reg(Ability("bachira_s2", "bachira", "skill", 3, "Golden Link",
            "「Passing is just dribbling with a friend.」",
            "Once per match: his next completed pass grants the receiver +2 on their following action.",
            pass_buff=2)),
    ]),
    ("reo", [
        _reg(Ability("reo_p1", "reo", "passive", 1, "Chameleon Copy",
            "「Show me something good — I'll steal it.」",
            "Passive: +1 to all duel powers when at least one SSR star stands against him.",
            att=lambda c: 1 if _foe_rarity("SSR")(c) else 0)),
        _reg(Ability("reo_s1", "reo", "skill", 1, "Perfect Mimicry",
            "「Everything you can do, money can learn.」",
            "Gamble: roll when you arm it — on a 3+ his copied footwork surges past the marker without a fight. A 1-2 shows the copy was only half-learned: possession lost.",
            gamble=True, gamble_min=3, when=lambda c: True)),
        _reg(Ability("reo_p2", "reo", "passive", 2, "All-Round Rise",
            "「Elite is a baseline, not a ceiling.」",
            "Passive: +1 to all his duel powers, always.",
            att=lambda c: 1)),
        _reg(Ability("reo_s2", "reo", "skill", 3, "Twin Engines",
            "「Nagi! One more time — like back then!」",
            "Once per match: with Seishiro Nagi beside him, +3 on his current action as the duo synchronizes.",
            att=lambda c: 3 if _mate("nagi")(c) else 0)),
    ]),
    ("hiori", [
        _reg(Ability("hiori_p1", "hiori", "passive", 1, "Silent Service",
            "「I see the run before you make it.」",
            "Passive: his completed passes grant the receiver +1 on their following action.",
            pass_buff=1)),
        _reg(Ability("hiori_s1", "hiori", "skill", 1, "Log-Out Ball",
            "「This pass ends the argument.」",
            "Once per match: the escape hatch — his pass can't be intercepted and the receiver breaks one zone forward.",
            pass_advance=1, when=lambda c: c["action"] == "pass")),
        _reg(Ability("hiori_p2", "hiori", "passive", 2, "Reading Room",
            "「Games are won between the ears first.」",
            "Passive: +1 Meta Vision-based defense whenever he's the one marking.",
            dfd=lambda c: 1)),
        _reg(Ability("hiori_s2", "hiori", "skill", 3, "Draw the Foul",
            "「He touched me. You all saw it.」",
            "Once per match: when he loses a field duel, he sells the contact — his team wins the set piece.",
            on_lost="foul")),
    ]),
    ("otoya", [
        _reg(Ability("otoya_p1", "otoya", "passive", 1, "Ninja Gap",
            "「You won't even hear me arrive.」",
            "+2 Shot when he escapes attention entirely (no marker).",
            att=lambda c: 2 if c["action"] == "shoot" and _unmarked(c) else 0)),
        _reg(Ability("otoya_s1", "otoya", "skill", 1, "Backstab",
            "「Shinobi rule one: strike the moment they relax.」",
            "Once per match: materializes inside a passing lane — intercepts without any dice.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("otoya_p2", "otoya", "passive", 2, "First Strike",
            "「The opening move decides the fight.」",
            "+2 to his first duel of every single attack.",
            att=lambda c: 2 if _first_link(c) else 0)),
        _reg(Ability("otoya_s2", "otoya", "skill", 3, "Shadow Step",
            "「One breath. One blade. One goal.」",
            "Gamble: roll a die when you arm it — that's how many unmarked runners he ghosts past this attack (min 1). Works on dribbles and runs.",
            gamble=True, when=lambda c: c["action"] == "dribble")),
    ]),
    ("karasu", [
        _reg(Ability("karasu_p1", "karasu", "passive", 1, "Crow's Read",
            "「I've seen this move a hundred times. Boring.」",
            "+1 Meta Vision-based defense whenever he marks an opponent.",
            dfd=lambda c: 1)),
        _reg(Ability("karasu_s1", "karasu", "skill", 1, "Kill the Pass Lane",
            "「Yeah yeah, I knew where it was going.」",
            "Once per match: snuffs out an opponent pass before it leaves the boot — no dice needed.",
            auto="stop", when=lambda c: c["action"] == "pass")),
        _reg(Ability("karasu_p2", "karasu", "passive", 2, "Game Management",
            "「Losing? Then we change the script.」",
            "+1 to attack and +1 to defense while his team is behind.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("karasu_s2", "karasu", "skill", 3, "Checkmate Call",
            "「Your eyes told me everything.」",
            "Once per match: when he takes a penalty, his read is so perfect the keeper is sent the wrong way — guaranteed goal.",
            pen_autoscore=True)),
    ]),
    ("yukimiya", [
        _reg(Ability("yukimiya_p1", "yukimiya", "passive", 1, "Orbital Shift",
            "「My rhythm orbits outside your reach.」",
            "+2 Dribble when operating in the Final Third.",
            att=lambda c: 2 if c["action"] == "dribble" and c["zone"] == ZONE_SHOOT else 0)),
        _reg(Ability("yukimiya_s1", "yukimiya", "skill", 1, "Blind Speed Burst",
            "「Even without sight — nobody catches me.」",
            "Once per match: explosive acceleration beats his marker without rolling.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("yukimiya_p2", "yukimiya", "passive", 2, "F-Sequence",
            "「Fifty moves, chained flawlessly.」",
            "His dice never show less than 2 — technical security netting every exchange.",
            die_floor=2)),
        _reg(Ability("yukimiya_s2", "yukimiya", "skill", 3, "Knight's Blade",
            "「The prince ends the fairy tale.」",
            "Once per match: his shot slices straight through the marker AND the keeper plays −2 against it.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=2,
            when=lambda c: c["action"] == "shoot")),
    ]),
    ("kunigami", [
        _reg(Ability("kunigami_p1", "kunigami", "passive", 1, "Hero Power",
            "「A hero's shot never wobbles.」",
            "+1 Shot and +1 Free Kick power — raw striking conviction.",
            att=lambda c: 1 if c["action"] in ("shoot", "freekick") else 0)),
        _reg(Ability("kunigami_s1", "kunigami", "skill", 1, "Wild Card Volley",
            "「This is what a hero looks like!」",
            "Once per match: a hero's second wind — the next action of ANY teammate gains +2, and his own shot gains +1 too.",
            pass_buff=2, att=lambda c: 1 if c["action"] == "shoot" else 0)),
        _reg(Ability("kunigami_p2", "kunigami", "passive", 2, "Never Back Down",
            "「Heroes don't lose twice.」",
            "+2 Shot while his team is trailing.",
            att=lambda c: 2 if c["action"] == "shoot" and _losing(c) else 0)),
        _reg(Ability("kunigami_s2", "kunigami", "passive", 3, "Captain's Wall",
            "「Nothing gets past us today.」",
            "While he's on the pitch, his team's keeper effectively plays +1 stronger — a leader's presence organizes the whole box.",
            aura_gk=1)),
    ]),
    # ---------------------------------------------------------------- R
    ("aryu", [
        _reg(Ability("aryu_p1", "aryu", "passive", 1, "Elegant Reach",
            "「Ugly efforts can't pass through beauty.」",
            "+1 defense against dribbles — those long limbs sweep the ball away gracefully.",
            dfd=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("aryu_s1", "aryu", "skill", 1, "Aesthetic Block",
            "「How vulgar. How… stopped.」",
            "Once per match: denies an opponent with immaculate positioning — no dice required.",
            auto="stop")),
        _reg(Ability("aryu_p2", "aryu", "passive", 2, "Model Frame",
            "「Proportions win duels.」",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("aryu_s2", "aryu", "skill", 3, "Aesthetic Aria",
            "「Beauty from distance — frame it.」",
            "Once per match: on his direct free kick, a tie with the keeper goes HIS way — artistry gets the benefit of the doubt.",
            att=lambda c: 1 if c["action"] == "freekick" else 0, tie_win=True,
            when=lambda c: c["action"] == "freekick")),
    ]),
    ("gagamaru", [
        _reg(Ability("gagamaru_p1", "gagamaru", "passive", 1, "Instinct Guard",
            "「My body moves before my brain does.」",
            "While he's on the pitch, his team's keeper effectively plays +1 stronger.",
            aura_gk=1)),
        _reg(Ability("gagamaru_s1", "gagamaru", "skill", 1, "Beast Reflex",
            "「Something told me to jump there.」",
            "Once per match: pure animal instinct shuts down an opponent cold — no dice.",
            auto="stop")),
        _reg(Ability("gagamaru_p2", "gagamaru", "passive", 2, "Acrobatic Clearance",
            "「Any shape, any save.」",
            "+1 Meta Vision-based defense whenever he marks.",
            dfd=lambda c: 1)),
        _reg(Ability("gagamaru_s2", "gagamaru", "skill", 3, "Last Line Claim",
            "「Mine. All of it.」",
            "Once per match: when his team's keeper punches the ball clear, Gagamaru claims the loose ball for his side.",
            punch_to_self=True)),
    ]),
    ("raichi", [
        _reg(Ability("raichi_p1", "raichi", "passive", 1, "Mad Dog Press",
            "「Get OFF our pitch!」",
            "+1 defense specifically against dribblers who dare run at him.",
            dfd=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("raichi_s1", "raichi", "skill", 1, "Rage Tackle",
            "「RAAAAGH! Mine!」",
            "Once per match: a furious crunching tackle wins the ball outright — no dice.",
            auto="stop")),
        _reg(Ability("raichi_p2", "raichi", "passive", 2, "Momentum Fury",
            "「Every stop makes me angrier.」",
            "+1 defense for each stop he has already made this match (max +3).",
            dfd=lambda c: min(3, c["self_stops"]))),
        _reg(Ability("raichi_s2", "raichi", "skill", 3, "Warrior's Grit",
            "「You think I'm going down?!」",
            "Once per match: when he loses a field duel, he wins the free kick anyway — referees fear the bark.",
            on_lost="foul")),
    ]),
    ("iemon", [
        _reg(Ability("iemon_p1", "iemon", "passive", 1, "Anchor Presence",
            "「Calm heads build attacks.」",
            "+1 Passing when starting play from Midfield.",
            att=lambda c: 1 if c["action"] == "pass" and _mid(c) else 0)),
        _reg(Ability("iemon_s1", "iemon", "skill", 1, "Set-Piece Script",
            "「We drilled this exact routine all week.」",
            "Once per match, on HIS set piece: the rehearsed routine — keeper reads the wrong corner on penalties, or ties go his way on free kicks.",
            tie_win=True, pen_edge=2)),
        _reg(Ability("iemon_p2", "iemon", "passive", 2, "Cool Head",
            "「Level game? That's where veterans live.」",
            "+1 attack and +1 defense whenever the score is dead even.",
            att=lambda c: 1 if _level(c) else 0,
            dfd=lambda c: 1 if _level(c) else 0)),
        _reg(Ability("iemon_s2", "iemon", "skill", 3, "Game Script",
            "「Seen that trick a decade ago, kid.」",
            "Gamble: roll when you arm it — on a 3+ the rehearsed page carries his pass or dribble past the marker without a fight. A 1-2 means the script was wrong: possession lost.",
            gamble=True, gamble_min=3, when=lambda c: c["action"] in ("pass", "dribble"))),
    ]),
    ("naruhaya", [
        _reg(Ability("naruhaya_p1", "naruhaya", "passive", 1, "Feint Master",
            "「Watch close — you'll buy it twice.」",
            "+2 Dribble on the first duel of each attack, when markers are freshest and most naive.",
            att=lambda c: 2 if c["action"] == "dribble" and _first_link(c) else 0)),
        _reg(Ability("naruhaya_s1", "naruhaya", "skill", 1, "Scam Step",
            "「Sold ya!」",
            "Once per match: a shameless double-feint sends his marker the wrong way — no dice.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("naruhaya_p2", "naruhaya", "passive", 2, "Tireless Engine",
            "「Small body, infinite battery.」",
            "+1 Dribble once the match has passed its halfway mark — legs outlasting everyone.",
            att=lambda c: 1 if c["action"] == "dribble" and c["turn"] * 2 > c["limit"] else 0)),
        _reg(Ability("naruhaya_s2", "naruhaya", "skill", 3, "Grand Scam",
            "「Contact? What contact… ow, MY leg!」",
            "Gamble: roll when you arm it — on a 4+ the referee swallows the whistle and he ghosts past that many defenders without a fight; on 1-3 he's sold a dummy instead and loses the duel outright.",
            gamble=True, gamble_min=4, when=lambda c: c["action"] == "dribble")),
    ]),
    ("kurona", [
        _reg(Ability("kurona_p1", "kurona", "passive", 1, "Shark Instinct",
            "「Blood in the water — accelerate.」",
            "+1 Dribble at all times, a constant low hum of danger.",
            att=lambda c: 1 if c["action"] == "dribble" else 0)),
        _reg(Ability("kurona_s1", "kurona", "skill", 1, "Run Through",
            "「Straight line. No brakes.」",
            "Once per match: slices through his marker without rolling and gains an extra zone.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
        _reg(Ability("kurona_p2", "kurona", "passive", 2, "One-Touch Shot",
            "「Isagi's runs teach good habits.」",
            "+2 Shot when finishing immediately after receiving a pass.",
            att=lambda c: 2 if c["action"] == "shoot" and _after_pass(c) else 0)),
        _reg(Ability("kurona_s2", "kurona", "skill", 3, "Piranha Press",
            "「We hunt in packs — and alone.」",
            "Once per match: swarms a ball-carrier and strips him cleanly — no dice.",
            auto="stop", when=lambda c: c["action"] == "dribble")),
    ]),
    ("tokimitsu", [
        _reg(Ability("tokimitsu_p1", "tokimitsu", "passive", 1, "Anxiety Surge",
            "「If we lose, it's all my fault — so NO.」",
            "+2 to all duel powers while his team is losing — panic converts to horsepower.",
            att=lambda c: 2 if _losing(c) else 0)),
        _reg(Ability("tokimitsu_s1", "tokimitsu", "skill", 1, "Muscle Shield",
            "「Sorry — but you're NOT getting past.」",
            "Once per match: plants himself as an immovable object and shrugs off his marker without rolling.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("tokimitsu_p2", "tokimitsu", "passive", 2, "Iron Body",
            "「Built different. Literally.」",
            "+1 Meta Vision-based defense whenever he marks.",
            dfd=lambda c: 1)),
        _reg(Ability("tokimitsu_s2", "tokimitsu", "skill", 3, "Explosive Drive",
            "「All the anxiety leaves at once — FORWARD.」",
            "Once per match: a bulldozing surge that beats his marker without rolling and crashes two zones forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble")),
    ]),
    # ---------------------------------------------------------------- N
    ("wanima_a", [
        _reg(Ability("wanima_a_p1", "wanima_a", "passive", 1, "Twin Sync",
            "「He knows. I know. Nobody else does.」",
            "+1 to all duel powers while his twin Jyngo is on the same team.",
            att=lambda c: 1 if _mate("wanima_j")(c) else 0)),
        _reg(Ability("wanima_a_s1", "wanima_a", "skill", 1, "Overlap Run",
            "「Call it — I'm already running.」",
            "Once per match: the rehearsed burst beats his marker without rolling — telepathy at full sprint.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("wanima_a_p2", "wanima_a", "passive", 2, "Chemistry",
            "「Ten years of passes between us.」",
            "+2 Passing while his twin is on the pitch with him.",
            att=lambda c: 2 if c["action"] == "pass" and _mate("wanima_j")(c) else 0)),
        _reg(Ability("wanima_a_s2", "wanima_a", "skill", 3, "Twin Magic",
            "「One mind, two bodies.」",
            "Once per match: on his pass, exact ties with the interceptor go HIS way — ten years of timing beats the level ball.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("wanima_j", [
        _reg(Ability("wanima_j_p1", "wanima_j", "passive", 1, "Twin Sync",
            "「He knows. I know. Nobody else does.」",
            "+1 to all duel powers while his twin Keisuke is on the same team.",
            att=lambda c: 1 if _mate("wanima_a")(c) else 0)),
        _reg(Ability("wanima_j_s1", "wanima_j", "skill", 1, "Overlap Run",
            "「Call it — I'm already running.」",
            "Once per match: the rehearsed burst beats his marker without rolling — telepathy at full sprint.",
            auto="win", when=lambda c: c["action"] == "dribble")),
        _reg(Ability("wanima_j_p2", "wanima_j", "passive", 2, "Chemistry",
            "「Ten years of passes between us.」",
            "+2 Passing while his twin is on the pitch with him.",
            att=lambda c: 2 if c["action"] == "pass" and _mate("wanima_a")(c) else 0)),
        _reg(Ability("wanima_j_s2", "wanima_j", "skill", 3, "Twin Magic",
            "「One mind, two bodies.」",
            "Once per match: on his pass, exact ties with the interceptor go HIS way — ten years of timing beats the level ball.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("igaguri", [
        _reg(Ability("igaguri_p1", "igaguri", "passive", 1, "Tryhard Heart",
            "「Effort is my talent!」",
            "His dice never show less than 2 — sheer stubbornness salvages bad rolls.",
            die_floor=2)),
        _reg(Ability("igaguri_s1", "igaguri", "skill", 1, "Miracle Hustle",
            "「I'll chase down EVERY loose ball!」",
            "Once per match: hustle pays — he beats the marker without rolling, no matter the action.",
            auto="win")),
        _reg(Ability("igaguri_p2", "igaguri", "passive", 2, "Grind Mode",
            "「Behind on the scoreboard? More reason to run.」",
            "+1 to all duel powers while his team is losing.",
            att=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("igaguri_s2", "igaguri", "skill", 3, "Destiny Shove",
            "「Even fate respects effort!」",
            "Once per match: when he loses a field duel, the referee calls the foul his way — destiny rewarded.",
            on_lost="foul")),
    ]),
    ("hyoma_k", [
        _reg(Ability("hyoma_k_p1", "hyoma_k", "passive", 1, "Selfless Lane",
            "「Someone has to do the dirty work.」",
            "+2 Passing when building from Midfield.",
            att=lambda c: 2 if c["action"] == "pass" and _mid(c) else 0)),
        _reg(Ability("hyoma_k_s1", "hyoma_k", "skill", 1, "Decoy Run",
            "「Watch me, not him.」",
            "Once per match: drags two markers away — his next completed pass grants the receiver +2.",
            pass_buff=2)),
        _reg(Ability("hyoma_k_p2", "hyoma_k", "passive", 2, "Workhorse",
            "「Tired? After the whistle.」",
            "+1 attack and +1 defense while his team is behind.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0)),
        _reg(Ability("hyoma_k_s2", "hyoma_k", "skill", 3, "Killer Key",
            "「All game for this one ball.」",
            "Once per match: the unlocking pass — exact ties with the interceptor go HIS way, the one ball that never gets cut out on the level.",
            tie_win=True, when=lambda c: c["action"] == "pass")),
    ]),
    ("yuki", [
        _reg(Ability("yuki_p1", "yuki", "passive", 1, "Quiet Focus",
            "「Noise fades. Fundamentals hold.」",
            "+1 defense against passes — disciplined positional sense.",
            dfd=lambda c: 1 if c["action"] == "pass" else 0)),
        _reg(Ability("yuki_s1", "yuki", "skill", 1, "Ice Vein",
            "「Zero heartbeat. Zero mistakes.」",
            "Once per match, with the score dead level: his dice can't show less than 4 this attack — ice-cold precision.",
            die_floor=4, when=lambda c: _level(c))),
        _reg(Ability("yuki_p2", "yuki", "passive", 2, "Unshakeable",
            "「Pressure is a rumor.」",
            "His dice never show less than 2 — nothing rattles him.",
            die_floor=2)),
        _reg(Ability("yuki_s2", "yuki", "skill", 3, "Clutch Minute",
            "「Final minutes belong to the calm.」",
            "Once per match: while the game hangs in the balance (level or one goal either way), his shot ignores the keeper's die entirely — total vs power alone.",
            att=lambda c: 2 if abs(c["diff"]) <= 1 else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and abs(c["diff"]) <= 1)),
    ]),
    ("kira", [
        _reg(Ability("kira_p1", "kira", "passive", 1, "Fallen Ace",
            "「They forgot who I was. Remind them.」",
            "+2 Shot when attacking from the Final Third onward.",
            att=lambda c: 2 if c["action"] == "shoot" and _final(c) else 0)),
        _reg(Ability("kira_s1", "kira", "skill", 1, "Redemption Strike",
            "「One goal rewrites the whole story.」",
            "Once per match: the strike of a man with something to prove — while trailing, his shot gains +3; while level or ahead, +1 and the keeper plays −1.",
            att=lambda c: 3 if c["action"] == "shoot" and _losing(c) else 1 if c["action"] == "shoot" else 0,
            gk_down=1,
            when=lambda c: c["action"] == "shoot")),
        _reg(Ability("kira_p2", "kira", "passive", 2, "Chip on Shoulder",
            "「Stars fall UP.」",
            "+1 to all duel powers when facing at least one SSR opponent.",
            att=lambda c: 1 if _foe_rarity("SSR")(c) else 0)),
        _reg(Ability("kira_s2", "kira", "skill", 3, "Star Reborn",
            "「Supernovas end in light.」",
            "Once per match: +1 Shot AND the keeper's effective power drops by 2 on his strike.",
            att=lambda c: 1 if c["action"] == "shoot" else 0, gk_down=2)),
    ]),
]

for char_key, items in _KITS:
    STARTERS[char_key] = [ab.id for ab in items if ab.tier == 1]
    BY_CHAR[char_key] = items

from .abilities_extra import register_extras as _register_extras

_register_extras()


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
