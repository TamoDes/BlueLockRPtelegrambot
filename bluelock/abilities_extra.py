from .abilities import (
    BY_CHAR,
    REGISTRY,
    ZONE_BOX,
    ZONE_SHOOT,
    Ability,
    _late,
    _losing,
    _mate,
    _unmarked,
)


def _register(char_key: str, items: list[Ability]) -> None:
    known = {ab.id for ab in BY_CHAR.get(char_key, [])}
    for ab in items:
        REGISTRY[ab.id] = ab
        if ab.id not in known:
            BY_CHAR.setdefault(char_key, []).append(ab)
            known.add(ab.id)


def register_extras() -> None:
    _register("isagi", [
        Ability("isagi_p3", "isagi", "passive", 3, "Stage Devourer",
            "「The bigger the stage, the hungrier I get.」",
            "+1 to ALL duel powers whenever the game is level or his team is behind.",
            att=lambda c: 1 if c["diff"] <= 0 else 0),
        Ability("isagi_s3", "isagi", "skill", 4, "Devour the Match",
            "「This ending was part of my formula all along.」",
            "Once per match: his shot scores even if the keeper beats his total by up to 2 — the play is devoured whole.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("rin", [
        Ability("rin_p3", "rin", "passive", 3, "Perfectionist",
            "「Flaws are for other people.」",
            "+1 to attack AND +1 to defense at all times — complete everywhere.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("rin_s3", "rin", "skill", 4, "Itoshi Genesis",
            "「This strike ends the argument.」",
            "ULTIMATE: his shot ignores the marker entirely AND the keeper's die — pure power vs raw power alone.",
            gk_down=6, att=lambda c: 2 if c["action"] == "shoot" else 0,
            when=lambda c: c["action"] == "shoot"),
    ])
    _register("sae", [
        Ability("sae_p3", "sae", "passive", 3, "Orchestra Conductor",
            "「Everyone dances to my tempo.」",
            "His completed passes grant receivers +2, and he gains +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("sae_s3", "sae", "skill", 4, "Genius Masterpiece",
            "「World-class? No — this is beyond it.」",
            "ULTIMATE: the perfect ball — uninterceptable, and the receiver lands with the play already two zones advanced.",
            pass_advance=2, when=lambda c: c["action"] == "pass"),
    ])
    _register("kaiser", [
        Ability("kaiser_p3", "kaiser", "passive", 3, "Emperor's Court",
            "「Whole stadium — kneel.」",
            "+1 Shot, and while he plays his team's keeper effectively gains +1.",
            att=lambda c: 1 if c["action"] == "shoot" else 0, aura_gk=1),
        Ability("kaiser_s3", "kaiser", "skill", 4, "Kaiser Impact: Magnus",
            "「There exists no net that can stop this.」",
            "Once per match: his shot strikes so hard the keeper's effective power drops by 3.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
    ])
    _register("nagi", [
        Ability("nagi_p3", "nagi", "passive", 3, "Genius Reflexes",
            "「Even lazy eyes see everything.」",
            "+2 defense against dribbles and +1 Dribble on his own carries.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0,
            att=lambda c: 1 if c["action"] == "dribble" else 0),
        Ability("nagi_s3", "nagi", "skill", 4, "Ultra Miracle Trap",
            "「That was… really amazing, actually.」",
            "Once per match: an impossible touch beats marker OR keeper-phase pressure — auto-wins a dribble or a shot duel, carrying an extra zone on carries.",
            auto="win", zone_extra=1,
            when=lambda c: c["action"] in ("dribble", "shoot")),
    ])
    _register("shidou", [
        Ability("shidou_p3", "shidou", "passive", 3, "Box Demon",
            "「Six yards? That's my living room.」",
            "+2 Shot inside the box — stacking with Box Predator into a monstrous +4.",
            att=lambda c: 2 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("shidou_s3", "shidou", "skill", 4, "Devil's Finale",
            "「Even your miracle only feeds mine.」",
            "Once per match: his shot hits harder (keeper −1) AND rebounds to him if punched clear.",
            gk_down=1, save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("barou", [
        Ability("barou_p3", "barou", "passive", 3, "Tyrant's Aura",
            "「Kings do not share the pitch. They own it.」",
            "+1 to attack AND +1 to defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("barou_s3", "barou", "skill", 4, "King's Decree",
            "「Out of MY kingdom.」",
            "Once per match: brushes aside any marker without rolling when he pulls the trigger.",
            auto="win", when=lambda c: c["action"] == "shoot"),
    ])
    _register("chigiri", [
        Ability("chigiri_p3", "chigiri", "passive", 3, "Limit Break",
            "「My top speed has no top speed.」",
            "+1 Dribble and +1 Shot at all times.",
            att=lambda c: 1 if c["action"] in ("dribble", "shoot") else 0),
        Ability("chigiri_s3", "chigiri", "skill", 4, "Full-Throttle Finish",
            "「Eleven seconds? Try three.」",
            "Once per match: an uncatchable burst wins the duel without dice AND rockets him two extra zones up the pitch.",
            auto="win", zone_extra=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("bachira", [
        Ability("bachira_p3", "bachira", "passive", 3, "Monster Fusion",
            "「We're not taking turns anymore. We're one.」",
            "+1 Dribble, and his completed passes grant receivers +1.",
            att=lambda c: 1 if c["action"] == "dribble" else 0, pass_buff=1),
        Ability("bachira_s3", "bachira", "skill", 4, "Demonic Showtime",
            "「You wanted the monster? HERE'S THE MONSTER.」",
            "Gamble: roll the die — the monster carries him past that many defenders with pure chaos. But roll a 1 and the show turns into a horror movie: possession lost.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("reo", [
        Ability("reo_p3", "reo", "passive", 3, "Perfect Elite",
            "「Money bought perfection. Worth every yen.」",
            "+1 to ALL duel powers and +1 on penalty nerve checks.",
            att=lambda c: 1, pen_edge=1),
        Ability("reo_s3", "reo", "skill", 4, "Copy of the Ace",
            "「Everything you've built — I'll surpass it now.」",
            "ULTIMATE: perfect mimicry — copies the opposing team's best move this match. Unmarks himself, wins the duel, and ties go his way.",
            auto="win", tie_win=True),
    ])
    _register("hiori", [
        Ability("hiori_p3", "hiori", "passive", 3, "Field General",
            "「I don't shout orders. The ball gives them.」",
            "Completed passes grant receivers +2, and he gains +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("hiori_s3", "hiori", "skill", 4, "Holographic Ball",
            "「Look up. It's already there.」",
            "Once per match: his next completed pass grants the receiver a massive +4 on their following action.",
            pass_buff=4),
    ])
    _register("otoya", [
        Ability("otoya_p3", "otoya", "passive", 3, "Shadow Master",
            "「Presence is a choice. I decline.」",
            "+1 Meta Vision defense always, and +1 to all attacks made without a marker.",
            dfd=lambda c: 1,
            att=lambda c: 1 if _unmarked(c) else 0),
        Ability("otoya_s3", "otoya", "skill", 4, "Vanish Act",
            "「Turn around. The ball's already gone.」",
            "Once per match: erases ANY opponent action cold — steal, block or interception without dice.",
            auto="stop"),
    ])
    _register("karasu", [
        Ability("karasu_p3", "karasu", "passive", 3, "Perfect Read",
            "「I've seen your next three moves. Spoiler: they fail.」",
            "+2 Meta Vision defense whenever he marks someone.",
            dfd=lambda c: 2),
        Ability("karasu_s3", "karasu", "skill", 4, "Crow's Gambit",
            "「Your eyes blinked. That's all I needed.」",
            "Once per match: +3 on his penalty nerve check — a mind game won before the run-up.",
            pen_edge=3),
    ])
    _register("yukimiya", [
        Ability("yukimiya_p3", "yukimiya", "passive", 3, "Complete Rhythm",
            "「Every duel moves to my beat.」",
            "+1 to ALL duel powers at all times.",
            att=lambda c: 1),
        Ability("yukimiya_s3", "yukimiya", "skill", 4, "Crescent Blaster",
            "「A curve worthy of a gallery.」",
            "Once per match: +3 Free Kick power, and ties on his direct free kicks go HIS way.",
            att=lambda c: 3 if c["action"] == "freekick" else 0, tie_win=True,
            when=lambda c: c["action"] == "freekick"),
    ])
    _register("kunigami", [
        Ability("kunigami_p3", "kunigami", "passive", 3, "Hero's Banner",
            "「As long as I stand, the goal stands.」",
            "+1 Shot, and his team's keeper effectively plays +1 stronger — leadership at both ends (stacks with Captain's Wall).",
            att=lambda c: 1 if c["action"] == "shoot" else 0, aura_gk=1),
        Ability("kunigami_s3", "kunigami", "skill", 4, "Wild Hero Strike",
            "「THIS is what a hero looks like!」",
            "ULTIMATE: a thunderbolt — while trailing by one, his shot pierces both marker and keeper's die.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and c["diff"] == -1),
    ])
    _register("aryu", [
        Ability("aryu_p3", "aryu", "passive", 3, "Statuesque",
            "「Beauty does not chase. Beauty waits.」",
            "+1 Meta Vision defense always, and +1 Free Kick power on his own dead balls.",
            dfd=lambda c: 1,
            att=lambda c: 1 if c["action"] == "freekick" else 0),
        Ability("aryu_s3", "aryu", "skill", 4, "Sublime Volley",
            "「Frame this moment.」",
            "Once per match: a picture-perfect strike beats any marker without rolling.",
            auto="win", when=lambda c: c["action"] == "shoot"),
    ])
    _register("gagamaru", [
        Ability("gagamaru_p3", "gagamaru", "passive", 3, "Beast Mode",
            "「My instincts eat tactics for breakfast.」",
            "+1 Meta Vision defense, and his team's keeper effectively gains another +1 (stacks to +2 total).",
            dfd=lambda c: 1, aura_gk=1),
        Ability("gagamaru_s3", "gagamaru", "skill", 4, "Guardian Territory",
            "「Nothing passes here. NOTHING.」",
            "Once per match: one colossal defensive stand with +3 Meta Vision.",
            dfd=lambda c: 3),
    ])
    _register("raichi", [
        Ability("raichi_p3", "raichi", "passive", 3, "Warpath",
            "「Ninety minutes of NOISE.」",
            "+1 to attack AND +1 to defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("raichi_s3", "raichi", "skill", 4, "Explosion of Wrath",
            "「YOU SHALL NOT PASS!!」",
            "Once per match: one furious defensive stand with +3 Meta Vision.",
            dfd=lambda c: 3),
    ])
    _register("iemon", [
        Ability("iemon_p3", "iemon", "passive", 3, "Professor Football",
            "「Textbook — written by me.」",
            "Completed passes grant receivers +2, and he gains +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("iemon_s3", "iemon", "skill", 4, "Drilled Perfection",
            "「Two hundred repetitions. Every week.」",
            "Once per match: +3 on his penalty nerve check — rehearsed until flawless.",
            pen_edge=3),
    ])
    _register("naruhaya", [
        Ability("naruhaya_p3", "naruhaya", "passive", 3, "Endless Scam",
            "「Third feint's free!」",
            "+1 Dribble always, and +1 Meta Vision defense when he marks.",
            att=lambda c: 1 if c["action"] == "dribble" else 0, dfd=lambda c: 1),
        Ability("naruhaya_s3", "naruhaya", "skill", 4, "Mirage Step",
            "「Which one was real? Trick question.」",
            "Gamble: roll the die — that's how many defenders buy the mirage (min 2). Roll a 1 and there was never a mirage: the whole pitch saw through him.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("kurona", [
        Ability("kurona_p3", "kurona", "passive", 3, "Shark Frenzy",
            "「Forward. Always forward.」",
            "+1 to ALL actions launched from the Final Third onward.",
            att=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("kurona_s3", "kurona", "skill", 4, "Frenzy Press",
            "「Bite first. Apologize never.」",
            "Once per match: swallows ANY opponent action whole — steal, block or interception without dice.",
            auto="stop"),
    ])
    _register("tokimitsu", [
        Ability("tokimitsu_p3", "tokimitsu", "passive", 3, "Anxiety Engine",
            "「If I panic fast enough, it becomes speed.」",
            "+1 to ALL duel powers always, and +1 more to defense while his team trails.",
            att=lambda c: 1, dfd=lambda c: 1 if _losing(c) else 0),
        Ability("tokimitsu_s3", "tokimitsu", "skill", 4, "Unstoppable Momentum",
            "「Sorry — brakes were never installed.」",
            "Once per match: the first tackle against him simply fails — he keeps the ball and still advances.",
            tackle_keep=True),
    ])
    _register("wanima_a", [
        Ability("wanima_a_p3", "wanima_a", "passive", 3, "Twin Telepathy",
            "「One brain, two jerseys.」",
            "+1 to attack and +1 to defense while his twin shares the pitch.",
            att=lambda c: 1 if _mate("wanima_j")(c) else 0,
            dfd=lambda c: 1 if _mate("wanima_j")(c) else 0),
        Ability("wanima_a_s3", "wanima_a", "skill", 4, "Mirror Play",
            "「He passes to where I already am.」",
            "ULTIMATE (with twin nearby): the telepathic play — his pass cannot be intercepted and the receiver breaks TWO zones forward with it.",
            pass_advance=2, when=lambda c: c["action"] == "pass" and _mate("wanima_j")(c)),
    ])
    _register("wanima_j", [
        Ability("wanima_j_p3", "wanima_j", "passive", 3, "Twin Telepathy",
            "「One brain, two jerseys.」",
            "+1 to attack and +1 to defense while his twin shares the pitch.",
            att=lambda c: 1 if _mate("wanima_a")(c) else 0,
            dfd=lambda c: 1 if _mate("wanima_a")(c) else 0),
        Ability("wanima_j_s3", "wanima_j", "skill", 4, "Mirror Play",
            "「He passes to where I already am.」",
            "ULTIMATE (with twin nearby): the telepathic play — his pass cannot be intercepted and the receiver breaks TWO zones forward with it.",
            pass_advance=2, when=lambda c: c["action"] == "pass" and _mate("wanima_a")(c)),
    ])
    _register("igaguri", [
        Ability("igaguri_p3", "igaguri", "passive", 3, "Never-Say-Die",
            "「Talent loses to people who refuse to lose.」",
            "+1 to attack and +1 to defense while his team is behind.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0),
        Ability("igaguri_s3", "igaguri", "skill", 4, "Destiny Overdrive",
            "「Effort is a skill — and mine is maxed out!」",
            "ULTIMATE: destiny bends to hustle — while trailing, ANY action of his wins outright, no dice, no debate.",
            auto="win", when=lambda c: _losing(c)),
    ])
    _register("hyoma_k", [
        Ability("hyoma_k_p3", "hyoma_k", "passive", 3, "Unsung Engine",
            "「Do the work. Skip the applause.」",
            "+1 to ALL duel powers, and completed passes grant receivers +1.",
            att=lambda c: 1, pass_buff=1),
        Ability("hyoma_k_s3", "hyoma_k", "skill", 4, "Golden Key",
            "「Eighty quiet minutes for ONE perfect ball.」",
            "Once per match: his next completed pass grants the receiver a huge +4 on their following action.",
            pass_buff=4),
    ])
    _register("yuki", [
        Ability("yuki_p3", "yuki", "passive", 3, "Mountain Mind",
            "「Storms pass. Mountains stay.」",
            "+1 Meta Vision defense whenever he marks an opponent.",
            dfd=lambda c: 1),
        Ability("yuki_s3", "yuki", "skill", 4, "Absolute Clutch",
            "「The final minutes are the quietest.」",
            "ULTIMATE: in the closing quarter his shot goes beyond the keeper's reach — the die is ignored, nerve vs power only.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and _late(c)),
    ])
    _register("kira", [
        Ability("kira_p3", "kira", "passive", 3, "Star's Grudge",
            "「Every doubter becomes fuel.」",
            "+1 to ALL duel powers — or +2 when facing at least one SSR star.",
            att=lambda c: 2 if "SSR" in c["foe_rarities"] else 1),
        Ability("kira_s3", "kira", "skill", 4, "Supernova",
            "「Fallen stars end as light — watch me burn.」",
            "Once per match: his shot blazes past a keeper whose effective power drops by 2.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
