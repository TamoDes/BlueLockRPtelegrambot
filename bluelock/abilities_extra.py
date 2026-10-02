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
    from .abilities import STARTERS

    if char_key not in STARTERS:
        # starters = passives only — skills start LOCKED and are bought later
        STARTERS[char_key] = [ab.id for ab in items if ab.tier == 1 and ab.kind == "passive"]
    known = {ab.id for ab in BY_CHAR.get(char_key, [])}
    for ab in items:
        REGISTRY[ab.id] = ab
        if ab.id not in known:
            BY_CHAR.setdefault(char_key, []).append(ab)
            known.add(ab.id)


def register_extras() -> None:
    _register("isagi", [
        Ability("isagi_p3", "isagi", "passive", 3, "Stage Devourer",
            "+1 to all duels while level or behind.",
            att=lambda c: 1 if c["diff"] <= 0 else 0),
        Ability("isagi_s3", "isagi", "skill", 4, "Devour the Match",
            "Shot scores even if the keeper beats his total by up to 2.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("rin", [
        Ability("rin_p3", "rin", "passive", 3, "Perfectionist",
            "+1 attack and +1 defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("rin_s3", "rin", "skill", 4, "Itoshi Genesis",
            "Shot ignores the marker AND the keeper's die.",
            gk_down=6, att=lambda c: 2 if c["action"] == "shoot" else 0,
            when=lambda c: c["action"] == "shoot"),
    ])
    _register("sae", [
        Ability("sae_p3", "sae", "passive", 3, "Orchestra Conductor",
            "Completed passes give receivers +2; +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("sae_s3", "sae", "skill", 4, "Genius Masterpiece",
            "Pass can't be intercepted; the receiver lands two zones advanced.",
            pass_advance=2, when=lambda c: c["action"] == "pass"),
    ])
    _register("kaiser", [
        Ability("kaiser_p3", "kaiser", "passive", 3, "Emperor's Court",
            "+1 Shot; team keeper plays +1 while he's on.",
            att=lambda c: 1 if c["action"] == "shoot" else 0, aura_gk=1),
        Ability("kaiser_s3", "kaiser", "skill", 4, "Kaiser Impact: Magnus",
            "Keeper −3 against his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
    ])
    _register("nagi", [
        Ability("nagi_p3", "nagi", "passive", 3, "Genius Reflexes",
            "+2 defense against dribbles; +1 Dribble on his carries.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0,
            att=lambda c: 1 if c["action"] == "dribble" else 0),
        Ability("nagi_s3", "nagi", "skill", 4, "Ultra Miracle Trap",
            "Auto-wins a dribble or shot duel; carries gain an extra zone.",
            auto="win", zone_extra=1,
            when=lambda c: c["action"] in ("dribble", "shoot")),
    ])
    _register("shidou", [
        Ability("shidou_p3", "shidou", "passive", 3, "Box Demon",
            "+2 Shot inside the box.",
            att=lambda c: 2 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("shidou_s3", "shidou", "skill", 4, "Devil's Finale",
            "Keeper −1 on his shot, and it rebounds to him if punched.",
            gk_down=1, save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("barou", [
        Ability("barou_p3", "barou", "passive", 3, "Tyrant's Aura",
            "+1 attack and +1 defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("barou_s3", "barou", "skill", 4, "King's Decree",
            "Brushes aside any marker with no roll when he shoots.",
            auto="win", when=lambda c: c["action"] == "shoot"),
    ])
    _register("chigiri", [
        Ability("chigiri_p3", "chigiri", "passive", 3, "Limit Break",
            "+1 Dribble and +1 Shot at all times.",
            att=lambda c: 1 if c["action"] in ("dribble", "shoot") else 0),
        Ability("chigiri_s3", "chigiri", "skill", 4, "Full-Throttle Finish",
            "Beats the duel with no roll + two extra zones.",
            auto="win", zone_extra=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("bachira", [
        Ability("bachira_p3", "bachira", "passive", 3, "Monster Fusion",
            "+1 Dribble; completed passes give receivers +1.",
            att=lambda c: 1 if c["action"] == "dribble" else 0, pass_buff=1),
        Ability("bachira_s3", "bachira", "skill", 4, "Demonic Showtime",
            "Gamble: beats that many defenders with no roll; roll a 1: possession lost.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("reo", [
        Ability("reo_p3", "reo", "passive", 3, "Perfect Elite",
            "+1 to all duels; his penalty sends the keeper the wrong way.",
            att=lambda c: 1, pen_edge=1),
        Ability("reo_s3", "reo", "skill", 4, "Copy of the Ace",
            "Copies the opponent's best move: unmarks himself, wins the duel, ties go his way.",
            auto="win", tie_win=True),
    ])
    _register("hiori", [
        Ability("hiori_p3", "hiori", "passive", 3, "Field General",
            "Completed passes give receivers +2; +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("hiori_s3", "hiori", "skill", 4, "Holographic Ball",
            "Completed pass gives the receiver +4 next action.",
            pass_buff=4),
    ])
    _register("otoya", [
        Ability("otoya_p3", "otoya", "passive", 3, "Shadow Master",
            "+1 Meta Vision defense always; +1 to attacks without a marker.",
            dfd=lambda c: 1,
            att=lambda c: 1 if _unmarked(c) else 0),
        Ability("otoya_s3", "otoya", "skill", 4, "Vanish Act",
            "Erases any opponent action with no roll (steal, block, interception).",
            auto="stop"),
    ])
    _register("karasu", [
        Ability("karasu_p3", "karasu", "passive", 3, "Perfect Read",
            "+2 Meta Vision defense while marking.",
            dfd=lambda c: 2),
        Ability("karasu_s3", "karasu", "skill", 4, "Crow's Gambit",
            "+3 — sends the keeper the wrong way on his penalty.",
            pen_edge=3),
    ])
    _register("yukimiya", [
        Ability("yukimiya_p3", "yukimiya", "passive", 3, "Complete Rhythm",
            "+1 to all duels at all times.",
            att=lambda c: 1),
        Ability("yukimiya_s3", "yukimiya", "skill", 4, "Crescent Blaster",
            "+3 Free Kick; ties go his way.",
            att=lambda c: 3 if c["action"] == "freekick" else 0, tie_win=True,
            when=lambda c: c["action"] == "freekick"),
    ])
    _register("kunigami", [
        Ability("kunigami_p3", "kunigami", "passive", 3, "Hero's Banner",
            "+1 Shot; team keeper plays +1 while he's on.",
            att=lambda c: 1 if c["action"] == "shoot" else 0, aura_gk=1),
        Ability("kunigami_s3", "kunigami", "skill", 4, "Wild Hero Strike",
            "While trailing by one: shot ignores marker and keeper's die.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and c["diff"] == -1),
    ])
    _register("aryu", [
        Ability("aryu_p3", "aryu", "passive", 3, "Statuesque",
            "+1 Meta Vision defense; +1 Free Kick on his dead balls.",
            dfd=lambda c: 1,
            att=lambda c: 1 if c["action"] == "freekick" else 0),
        Ability("aryu_s3", "aryu", "skill", 4, "Sublime Volley",
            "Beats any marker with no roll.",
            auto="win", when=lambda c: c["action"] == "shoot"),
    ])
    _register("gagamaru", [
        Ability("gagamaru_p3", "gagamaru", "passive", 3, "Beast Mode",
            "+1 Meta Vision defense; team keeper +1 more (total +2).",
            dfd=lambda c: 1, aura_gk=1),
        Ability("gagamaru_s3", "gagamaru", "skill", 4, "Guardian Territory",
            "One defensive stand with +3 Meta Vision.",
            dfd=lambda c: 3),
    ])
    _register("raichi", [
        Ability("raichi_p3", "raichi", "passive", 3, "Warpath",
            "+1 attack and +1 defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("raichi_s3", "raichi", "skill", 4, "Explosion of Wrath",
            "One defensive stand with +3 Meta Vision.",
            dfd=lambda c: 3),
    ])
    _register("iemon", [
        Ability("iemon_p3", "iemon", "passive", 3, "Professor Football",
            "Completed passes give receivers +2; +1 Meta Vision defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("iemon_s3", "iemon", "skill", 4, "Drilled Perfection",
            "+3 — sends the keeper the wrong way on his penalty.",
            pen_edge=3),
    ])
    _register("naruhaya", [
        Ability("naruhaya_p3", "naruhaya", "passive", 3, "Endless Scam",
            "+1 Dribble always; +1 Meta Vision defense while marking.",
            att=lambda c: 1 if c["action"] == "dribble" else 0, dfd=lambda c: 1),
        Ability("naruhaya_s3", "naruhaya", "skill", 4, "Mirage Step",
            "Gamble: that many defenders buy the mirage (min 2); roll a 1: no mirage, possession lost.",
            gamble=True, gamble_min=2, when=lambda c: c["action"] == "dribble"),
    ])
    _register("kurona", [
        Ability("kurona_p3", "kurona", "passive", 3, "Shark Frenzy",
            "+1 to all actions from the Final Third onward.",
            att=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("kurona_s3", "kurona", "skill", 4, "Frenzy Press",
            "Swallows any opponent action with no roll.",
            auto="stop"),
    ])
    _register("tokimitsu", [
        Ability("tokimitsu_p3", "tokimitsu", "passive", 3, "Anxiety Engine",
            "+1 to all duels; +1 more to defense while trailing.",
            att=lambda c: 1, dfd=lambda c: 1 if _losing(c) else 0),
        Ability("tokimitsu_s3", "tokimitsu", "skill", 4, "Unstoppable Momentum",
            "First tackle against him fails: keeps the ball and advances.",
            tackle_keep=True),
    ])
    _register("wanima_a", [
        Ability("wanima_a_p3", "wanima_a", "passive", 3, "Twin Telepathy",
            "+1 attack and +1 defense while his twin is on the pitch.",
            att=lambda c: 1 if _mate("wanima_j")(c) else 0,
            dfd=lambda c: 1 if _mate("wanima_j")(c) else 0),
        Ability("wanima_a_s3", "wanima_a", "skill", 4, "Mirror Play",
            "Pass can't be intercepted; the receiver breaks two zones (twin nearby).",
            pass_advance=2, when=lambda c: c["action"] == "pass" and _mate("wanima_j")(c)),
    ])
    _register("wanima_j", [
        Ability("wanima_j_p3", "wanima_j", "passive", 3, "Twin Telepathy",
            "+1 attack and +1 defense while his twin is on the pitch.",
            att=lambda c: 1 if _mate("wanima_a")(c) else 0,
            dfd=lambda c: 1 if _mate("wanima_a")(c) else 0),
        Ability("wanima_j_s3", "wanima_j", "skill", 4, "Mirror Play",
            "Pass can't be intercepted; the receiver breaks two zones (twin nearby).",
            pass_advance=2, when=lambda c: c["action"] == "pass" and _mate("wanima_a")(c)),
    ])
    _register("igaguri", [
        Ability("igaguri_p3", "igaguri", "passive", 3, "Never-Say-Die",
            "+1 attack and +1 defense while trailing.",
            att=lambda c: 1 if _losing(c) else 0,
            dfd=lambda c: 1 if _losing(c) else 0),
        Ability("igaguri_s3", "igaguri", "skill", 4, "Destiny Overdrive",
            "While trailing: any action wins outright with no roll.",
            auto="win", when=lambda c: _losing(c)),
    ])
    _register("hyoma_k", [
        Ability("hyoma_k_p3", "hyoma_k", "passive", 3, "Unsung Engine",
            "+1 to all duels; completed passes give receivers +1.",
            att=lambda c: 1, pass_buff=1),
        Ability("hyoma_k_s3", "hyoma_k", "skill", 4, "Golden Key",
            "Completed pass gives the receiver +4 next action.",
            pass_buff=4),
    ])
    _register("yuki", [
        Ability("yuki_p3", "yuki", "passive", 3, "Mountain Mind",
            "+1 Meta Vision defense while marking.",
            dfd=lambda c: 1),
        Ability("yuki_s3", "yuki", "skill", 4, "Absolute Clutch",
            "Last quarter: shot ignores the keeper's die.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=6,
            when=lambda c: c["action"] == "shoot" and _late(c)),
    ])
    _register("kira", [
        Ability("kira_p3", "kira", "passive", 3, "Star's Grudge",
            "+1 to all duels, or +2 against an SSR star.",
            att=lambda c: 2 if "SSR" in c["foe_rarities"] else 1),
        Ability("kira_s3", "kira", "skill", 4, "Supernova",
            "Keeper −2 against his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    # ----------------------------------------------------------------- newcomers
    _register("aiku", [
        Ability("aiku_p1", "aiku", "passive", 1, "Board Vision",
            "+1 defense on every duel.",
            dfd=lambda c: 1),
        Ability("aiku_s1", "aiku", "skill", 1, "Frozen Line",
            "Standing tackle erases the dribble with no roll.",
            auto="stop"),
        Ability("aiku_p2", "aiku", "passive", 2, "Clean Sheet Greed",
            "+2 defense while his team is ahead.",
            dfd=lambda c: 2 if c["diff"] > 0 else 0),
        Ability("aiku_s2", "aiku", "skill", 3, "Box Lockdown",
            "+3 when defending a shot.",
            dfd=lambda c: 3, when=lambda c: c["action"] == "shoot"),
        Ability("aiku_p3", "aiku", "passive", 3, "Captain\u2019s Gravity",
            "+1 to all duels while the score is level.",
            att=lambda c: 1 if c["diff"] == 0 else 0,
            dfd=lambda c: 1 if c["diff"] == 0 else 0),
        Ability("aiku_s3", "aiku", "skill", 4, "Absolute Lock",
            "Defensive stand: die never below 4 and +2 defense.",
            dfd=lambda c: 2, die_floor=4),
    ])
    _register("ness", [
        Ability("ness_p1", "ness", "passive", 1, "Supply Line",
            "Completed passes give the receiver +1 next action.",
            pass_buff=1),
        Ability("ness_s1", "ness", "skill", 1, "Golden Ball",
            "Completed pass sends the receiver one extra zone.",
            pass_advance=1),
        Ability("ness_p2", "ness", "passive", 2, "Loyal Engine",
            "+1 to all duels while Kaiser is on the pitch.",
            att=lambda c: 1 if _mate("kaiser") else 0,
            dfd=lambda c: 1 if _mate("kaiser") else 0),
        Ability("ness_s2", "ness", "skill", 3, "Set-Piece Darling",
            "+2 — sends the keeper the wrong way on his penalty.",
            pen_edge=2),
        Ability("ness_p3", "ness", "passive", 3, "Emperor\u2019s Shadow",
            "Completed passes give receivers +2; +1 defense on his marks.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("ness_s3", "ness", "skill", 4, "Forever Number 10",
            "Pass can't be intercepted; the receiver's next action +4.",
            pass_advance=1, pass_buff=4),
    ])
    _register("charles", [
        Ability("charles_p1", "charles", "passive", 1, "French Pass",
            "+2 on his pass; receiver's next action +1. If a goal follows, "
            "Charles and the scorer each take +1.",
            att=lambda c: 2 if c["action"] == "pass" else 0, pass_buff=1,
            goal_self=1, goal_mate=1),
        Ability("charles_s1", "charles", "skill", 1, "Switch of Play",
            "Completed pass: receiver breaks two zones.",
            pass_advance=2),
        Ability("charles_p2", "charles", "passive", 2, "Prodigy\u2019s Touch",
            "+2 on his dribble feints.",
            att=lambda c: 2 if c["action"] == "dribble" else 0),
        Ability("charles_s2", "charles", "skill", 3, "The Tease",
            "Stop his dribble → foul called: free kick.",
            on_lost="foul"),
        Ability("charles_p3", "charles", "passive", 3, "Charm Game",
            "+1 on his passes; completed passes give receivers +1.",
            att=lambda c: 1 if c["action"] == "pass" else 0, pass_buff=1),
        Ability("charles_s3", "charles", "skill", 4, "Trance Pass",
            "Pass breaks two zones; the receiver's next action +2.",
            pass_advance=2, pass_buff=2),
    ])
    _register("zantetsu", [
        Ability("zantetsu_p1", "zantetsu", "passive", 1, "Never Stalling",
            "Die never rolls below 2.",
            die_floor=2),
        Ability("zantetsu_s1", "zantetsu", "skill", 1, "Steel Dash",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble"),
        Ability("zantetsu_p2", "zantetsu", "passive", 2, "Blade\u2019s Edge",
            "+1 when he carries or strikes.",
            att=lambda c: 1 if c["action"] in ("dribble", "shoot") else 0),
        Ability("zantetsu_s2", "zantetsu", "skill", 3, "Iron Run",
            "Two zones carved in one burst.",
            auto="win", zone_extra=2, when=lambda c: c["action"] == "dribble"),
        Ability("zantetsu_p3", "zantetsu", "passive", 3, "Afterimage",
            "+2 on his dashes and +1 defense.",
            att=lambda c: 2 if c["action"] == "dribble" else 0, dfd=lambda c: 1),
        Ability("zantetsu_s3", "zantetsu", "skill", 4, "Unreachable",
            "Strike +2 power, keeper −3.",
            att=lambda c: 2 if c["action"] == "shoot" else 0, gk_down=3,
            when=lambda c: c["action"] == "shoot"),
    ])
