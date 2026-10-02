"""Starting kits for the 56 roster characters that had no abilities.

Auto-registered alongside the other ability packs — register_extras() only
appends to BY_CHAR / REGISTRY / STARTERS, so import order is irrelevant.
Every desc is pure mechanics (Taha's style rule): short stat-bullet English,
no narration, no FLOW references.
"""

from .abilities import (
    BY_CHAR,
    REGISTRY,
    STARTERS,
    ZONE_BOX,
    ZONE_SHOOT,
    Ability,
    _late,
    _losing,
    _mate,
    _unmarked,
)


def _register(char_key: str, items: list[Ability]) -> None:
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
    _register("achanpong", [
        Ability("achanpong_p1", "achanpong", "passive", 1, "Quarterback Reads",
            "+1 Pass; completed passes give receivers +1.",
            att=lambda c: 1 if c["action"] == "pass" else 0, pass_buff=1),
        Ability("achanpong_s1", "achanpong", "skill", 1, "Precision Delivery",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("achanpong_s2", "achanpong", "skill", 3, "Lock-On Volley",
            "Keeper −2 on his shot from inside the box.",
            gk_down=2, when=lambda c: c["action"] == "shoot" and c["zone"] >= ZONE_BOX),
    ])
    _register("agi", [
        Ability("agi_p1", "agi", "passive", 1, "Ice in the Veins",
            "+1 to all duels while level or behind.",
            att=lambda c: 1 if c["diff"] <= 0 else 0),
        Ability("agi_s1", "agi", "skill", 1, "Cold Switch",
            "Wins the duel outright with no roll.",
            auto="win"),
        Ability("agi_s2", "agi", "skill", 3, "Deadball Snipe",
            "Keeper −3 on his free kick.",
            gk_down=3, when=lambda c: c["action"] == "freekick"),
    ])
    _register("arthur", [
        Ability("arthur_p1", "arthur", "passive", 1, "Second Wind",
            "+1 defense in the final third.",
            dfd=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("arthur_s1", "arthur", "skill", 1, "Shoulder Charge",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("arthur_s2", "arthur", "skill", 3, "Late Arrival",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("bats", [
        Ability("bats_p1", "bats", "passive", 1, "Quick Link",
            "+1 Pass at all times.",
            att=lambda c: 1 if c["action"] == "pass" else 0),
        Ability("bats_s1", "bats", "skill", 1, "One-Two Burst",
            "Pass can't be intercepted; receiver lands two zones forward.",
            pass_advance=2),
        Ability("bats_s2", "bats", "skill", 3, "Trailing Shot",
            "Keeper −2; his shot rebounds to him if punched.",
            gk_down=2, save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("birkenstock", [
        Ability("birkenstock_p1", "birkenstock", "passive", 1, "Wall Stance",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("birkenstock_s1", "birkenstock", "skill", 1, "Iron Block",
            "Erases any shot with no roll.",
            auto="stop", when=lambda c: c["action"] == "shoot"),
        Ability("birkenstock_s2", "birkenstock", "skill", 3, "Denial",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("blake", [
        Ability("blake_p1", "blake", "passive", 1, "Raw Power",
            "+1 Shot inside the box.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("blake_s1", "blake", "skill", 1, "Cannon Fire",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
        Ability("blake_s2", "blake", "skill", 3, "Second Strike",
            "If his shot is saved, it rebounds to him.",
            save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("bos", [
        Ability("bos_p1", "bos", "passive", 1, "Steady Nerves",
            "+1 to all duels while losing.",
            att=lambda c: 1 if c["diff"] < 0 else 0),
        Ability("bos_s1", "bos", "skill", 1, "Quick Feet",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble"),
        Ability("bos_s2", "bos", "skill", 3, "Safe Pass",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
    ])
    _register("camus", [
        Ability("camus_p1", "camus", "passive", 1, "Volley Instinct",
            "+1 Shot in the final third.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_SHOOT else 0),
        Ability("camus_s1", "camus", "skill", 1, "Dipping Volley",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
        Ability("camus_s2", "camus", "skill", 3, "Chip Shot",
            "Shot scores even if the keeper beats him by 2.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("cavasoz", [
        Ability("cavasoz_p1", "cavasoz", "passive", 1, "Deadball Aura",
            "+2 on free kicks.",
            att=lambda c: 2 if c["action"] == "freekick" else 0),
        Ability("cavasoz_s1", "cavasoz", "skill", 1, "Screamer",
            "Keeper −3 on his free kick.",
            gk_down=3, when=lambda c: c["action"] == "freekick"),
        Ability("cavasoz_s2", "cavasoz", "skill", 3, "Top Corner",
            "Shot scores even if the keeper beats him by 2.",
            save_margin=2, when=lambda c: c["action"] in ("freekick", "shoot")),
    ])
    _register("chapa", [
        Ability("chapa_p1", "chapa", "passive", 1, "No-Nonsense",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
        Ability("chapa_s1", "chapa", "skill", 1, "Standing Tackle",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("chapa_s2", "chapa", "skill", 3, "Cover Shadow",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("chevalier", [
        Ability("chevalier_p1", "chevalier", "passive", 1, "Visionary",
            "Completed passes give receivers +2.",
            pass_buff=2),
        Ability("chevalier_s1", "chevalier", "skill", 1, "Switch of Play",
            "Pass can't be intercepted; receiver lands two zones forward.",
            pass_advance=2),
        Ability("chevalier_s2", "chevalier", "skill", 3, "First-Time Finish",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("childs", [
        Ability("childs_p1", "childs", "passive", 1, "Pace Abuse",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0),
        Ability("childs_s1", "childs", "skill", 1, "Explosive Dash",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("childs_s2", "childs", "skill", 3, "Near-Post Finish",
            "Keeper −2; his shot rebounds to him if punched.",
            gk_down=2, save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("cho", [
        Ability("cho_p1", "cho", "passive", 1, "Team Player",
            "+1 to all duels while level or behind.",
            att=lambda c: 1 if c["diff"] <= 0 else 0),
        Ability("cho_s1", "cho", "skill", 1, "Intercept",
            "Erases any pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass"),
        Ability("cho_s2", "cho", "skill", 3, "Box Clearance",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
    ])
    _register("delon", [
        Ability("delon_p1", "delon", "passive", 1, "Tireless",
            "+1 defense in the final third.",
            dfd=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("delon_s1", "delon", "skill", 1, "Last-Ditch Slide",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("delon_s2", "delon", "skill", 3, "Aerial Dominance",
            "+2 defense against crosses.",
            dfd=lambda c: 2 if c["action"] == "cross" else 0),
    ])
    _register("endoji", [
        Ability("endoji_p1", "endoji", "passive", 1, "Composure",
            "+1 to all duels while losing.",
            att=lambda c: 1 if c["diff"] < 0 else 0),
        Ability("endoji_s1", "endoji", "skill", 1, "Snap Tackle",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("endoji_s2", "endoji", "skill", 3, "Late Challenge",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("fukaku", [
        Ability("fukaku_p1", "fukaku", "passive", 1, "Safe Hands",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("fukaku_s1", "fukaku", "skill", 1, "Down Low",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
        Ability("fukaku_s2", "fukaku", "skill", 3, "Penalty Wall",
            "Erases any penalty with no roll.",
            auto="stop", when=lambda c: c["action"] == "penalty"),
    ])
    _register("gabin", [
        Ability("gabin_p1", "gabin", "passive", 1, "Positioning",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("gabin_s1", "gabin", "skill", 1, "Cutting Lane",
            "Erases any pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass"),
        Ability("gabin_s2", "gabin", "skill", 3, "Aggressive Press",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("gesner", [
        Ability("gesner_p1", "gesner", "passive", 1, "Engine Room",
            "+1 Pass at all times.",
            att=lambda c: 1 if c["action"] == "pass" else 0),
        Ability("gesner_s1", "gesner", "skill", 1, "Relay",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("gesner_s2", "gesner", "skill", 3, "Snap Shot",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("gomez", [
        Ability("gomez_p1", "gomez", "passive", 1, "Untiring",
            "+1 to all duels in the final third.",
            att=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("gomez_s1", "gomez", "skill", 1, "Shoulder Barge",
            "Wins the duel outright with no roll.",
            auto="win"),
        Ability("gomez_s2", "gomez", "skill", 3, "Recovery Run",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("goodman", [
        Ability("goodman_p1", "goodman", "passive", 1, "Reads the Game",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
        Ability("goodman_s1", "goodman", "skill", 1, "Crunching Tackle",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("goodman_s2", "goodman", "skill", 3, "Last Man",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("hermes", [
        Ability("hermes_p1", "hermes", "passive", 1, "Positional Play",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("hermes_s1", "hermes", "skill", 1, "Denying Foul",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("hermes_s2", "hermes", "skill", 3, "Recovery Pace",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("hiiragi", [
        Ability("hiiragi_p1", "hiiragi", "passive", 1, "Calm Finisher",
            "+1 Shot inside the box.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("hiiragi_s1", "hiiragi", "skill", 1, "Curled Effort",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
        Ability("hiiragi_s2", "hiiragi", "skill", 3, "One-Touch Finish",
            "Shot scores even if the keeper beats him by 2.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("hugo", [
        Ability("hugo_p1", "hugo", "passive", 1, "Phantom Pass/Shot",
            "His pass or shot wins the duel with no roll.",
            auto="win", when=lambda c: c["action"] in ("pass", "shoot")),
        Ability("hugo_s1", "hugo", "skill", 1, "Long Drive",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
        Ability("hugo_s2", "hugo", "skill", 3, "Wall Pass",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2),
    ])
    _register("igarashi", [
        Ability("igarashi_p1", "igarashi", "passive", 1, "Hustle",
            "+1 to all duels while losing.",
            att=lambda c: 1 if c["diff"] < 0 else 0),
        Ability("igarashi_s1", "igarashi", "skill", 1, "Scraping Tackle",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("igarashi_s2", "igarashi", "skill", 3, "Never Give Up",
            "First lost duel of the match doesn't count.",
            first_free=True),
    ])
    _register("iglesias", [
        Ability("iglesias_p1", "iglesias", "passive", 1, "Rabbit's Leap",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0),
        Ability("iglesias_s1", "iglesias", "skill", 1, "Burst of Speed",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("iglesias_s2", "iglesias", "skill", 3, "Backheel Trick",
            "Wins the duel outright with no roll.",
            auto="win"),
    ])
    _register("ishikari", [
        Ability("ishikari_p1", "ishikari", "passive", 1, "Frame",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("ishikari_s1", "ishikari", "skill", 1, "Aerial Clear",
            "Erases any cross with no roll.",
            auto="stop", when=lambda c: c["action"] == "cross"),
        Ability("ishikari_s2", "ishikari", "skill", 3, "Body on the Line",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
    ])
    _register("kiyora", [
        Ability("kiyora_p1", "kiyora", "passive", 1, "Ice Veins",
            "+1 Pass in the final third.",
            att=lambda c: 1 if c["action"] == "pass" and c["zone"] >= ZONE_SHOOT else 0),
        Ability("kiyora_s1", "kiyora", "skill", 1, "Surgical Ball",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("kiyora_s2", "kiyora", "skill", 3, "Clinch Strike",
            "Keeper −2 in the final third.",
            gk_down=2, when=lambda c: c["action"] == "shoot" and c["zone"] >= ZONE_SHOOT),
    ])
    _register("knight", [
        Ability("knight_p1", "knight", "passive", 1, "Knight Defense / Knight Sword",
            "+2 defending against a dribble; +1 on his dribble, +2 on his shot; "
            "+2 more if he scores.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0,
            att=lambda c: 1 if c["action"] == "dribble" else (2 if c["action"] == "shoot" else 0),
            goal_self=2),
        Ability("knight_s1", "knight", "skill", 1, "Complete Striker",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("knight_s2", "knight", "skill", 3, "Match Winner",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
    ])
    _register("kuso", [
        Ability("kuso_p1", "kuso", "passive", 1, "Tempo Control",
            "Completed passes give receivers +2.",
            pass_buff=2),
        Ability("kuso_s1", "kuso", "skill", 1, "Pulse Pass",
            "Pass can't be intercepted; receiver lands two zones forward.",
            pass_advance=2),
        Ability("kuso_s2", "kuso", "skill", 3, "Dictate",
            "+2 Pass on his next action.",
            att=lambda c: 2 if c["action"] == "pass" else 0),
    ])
    _register("lara", [
        Ability("lara_p1", "lara", "passive", 1, "Poacher's Instinct",
            "+1 Shot inside the box.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("lara_s1", "lara", "skill", 1, "Volley",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
        Ability("lara_s2", "lara", "skill", 3, "Rebound Hunter",
            "If his shot is saved, it rebounds to him.",
            save_self=True, when=lambda c: c["action"] == "shoot"),
    ])
    _register("lavinho", [
        Ability("lavinho_p1", "lavinho", "passive", 1, "Dance",
            "+3 on his dribble; walks past the whole defence and +2 if it ends in a goal.",
            att=lambda c: 3 if c["action"] == "dribble" else 0,
            through=99, goal_self=2),
        Ability("lavinho_s1", "lavinho", "skill", 1, "Elastica",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("lavinho_s2", "lavinho", "skill", 3, "Carnival Feint",
            "Wins the duel outright; ties go his way.",
            auto="win", tie_win=True),
    ])
    _register("leyden", [
        Ability("leyden_p1", "leyden", "passive", 1, "Deep Lying",
            "+1 Pass at all times.",
            att=lambda c: 1 if c["action"] == "pass" else 0),
        Ability("leyden_s1", "leyden", "skill", 1, "Switch",
            "Pass can't be intercepted; receiver lands two zones forward.",
            pass_advance=2),
        Ability("leyden_s2", "leyden", "skill", 3, "Rising Shot",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("loki", [
        Ability("loki_p1", "loki", "passive", 1, "Godspeed",
            "+1 Dribble and +1 Shot at all times.",
            att=lambda c: 1 if c["action"] in ("dribble", "shoot") else 0),
        Ability("loki_s1", "loki", "skill", 1, "Lightning Dash",
            "Beats his marker with no roll and lands two zones forward.",
            auto="win", zone_extra=2, when=lambda c: c["action"] == "dribble"),
        Ability("loki_s2", "loki", "skill", 3, "Devil's Sprint",
            "Wins the duel outright and lands one zone forward.",
            auto="win", zone_extra=1),
    ])
    _register("lorenzo", [
        Ability("lorenzo_p1", "lorenzo", "passive", 1, "Undead Dribble",
            "+2 Dribble at all times.",
            att=lambda c: 2 if c["action"] == "dribble" else 0),
        Ability("lorenzo_s1", "lorenzo", "skill", 1, "Zombie Step",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble"),
        Ability("lorenzo_s2", "lorenzo", "skill", 3, "Gravekeeper",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("luna", [
        Ability("luna_p1", "luna", "passive", 1, "Lunar Rhythm",
            "+1 Dribble and +1 Shot at all times.",
            att=lambda c: 1 if c["action"] in ("dribble", "shoot") else 0),
        Ability("luna_s1", "luna", "skill", 1, "Moonwalk",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("luna_s2", "luna", "skill", 3, "Crescent Shot",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
    ])
    _register("nanase", [
        Ability("nanase_p1", "nanase", "passive", 1, "Rainbow Runs",
            "+1 to all duels in the final third.",
            att=lambda c: 1 if c["zone"] >= ZONE_SHOOT else 0),
        Ability("nanase_s1", "nanase", "skill", 1, "Straight Line Dash",
            "Beats his marker with no roll.",
            auto="win", when=lambda c: c["action"] == "dribble"),
        Ability("nanase_s2", "nanase", "skill", 3, "Selfless Link",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2),
    ])
    _register("niang", [
        Ability("niang_p1", "niang", "passive", 1, "Byline Runs",
            "+1 Dribble in the final third.",
            att=lambda c: 1 if c["action"] == "dribble" and c["zone"] >= ZONE_SHOOT else 0),
        Ability("niang_s1", "niang", "skill", 1, "Whipped Ball",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2),
        Ability("niang_s2", "niang", "skill", 3, "Cut Inside",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("niko", [
        Ability("niko_p1", "niko", "passive", 1, "Anchor",
            "+2 defense at all times.",
            dfd=lambda c: 2),
        Ability("niko_s1", "niko", "skill", 1, "Cutting Interception",
            "Erases any pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass"),
        Ability("niko_s2", "niko", "skill", 3, "Screen",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
    ])
    _register("nio", [
        Ability("nio_p1", "nio", "passive", 1, "Holding Shape",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("nio_s1", "nio", "skill", 1, "Foul Play",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("nio_s2", "nio", "skill", 3, "Time the Tackle",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
    ])
    _register("nishioka", [
        Ability("nishioka_p1", "nishioka", "passive", 1, "Grit",
            "+1 to all duels while losing.",
            att=lambda c: 1 if c["diff"] < 0 else 0),
        Ability("nishioka_s1", "nishioka", "skill", 1, "Quick Interception",
            "Erases any pass with no roll.",
            auto="stop", when=lambda c: c["action"] == "pass"),
        Ability("nishioka_s2", "nishioka", "skill", 3, "Burst Pass",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
    ])
    _register("noa", [
        Ability("noa_p1", "noa", "passive", 1, "Complete Striker",
            "+1 attack and +1 defense at all times.",
            att=lambda c: 1, dfd=lambda c: 1),
        Ability("noa_s1", "noa", "skill", 1, "Noa's Finish",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
        Ability("noa_s2", "noa", "skill", 3, "Adapted Strike",
            "Shot scores even if the keeper beats him by 2.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("prince", [
        Ability("prince_p1", "prince", "passive", 1, "Perfect Physique",
            "+1 Dribble and +1 defense at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0, dfd=lambda c: 1),
        Ability("prince_s1", "prince", "skill", 1, "Power Drive",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
        Ability("prince_s2", "prince", "skill", 3, "Unbreakable",
            "First lost duel of the match doesn't count.",
            first_free=True),
    ])
    _register("renoir", [
        Ability("renoir_p1", "renoir", "passive", 1, "Shot Stopping",
            "+2 defense against shots.",
            dfd=lambda c: 2 if c["action"] == "shoot" else 0),
        Ability("renoir_s1", "renoir", "skill", 1, "Full Stretch",
            "Erases any shot with no roll.",
            auto="stop", when=lambda c: c["action"] == "shoot"),
        Ability("renoir_s2", "renoir", "skill", 3, "Claiming Crosses",
            "Erases any cross with no roll.",
            auto="stop", when=lambda c: c["action"] == "cross"),
    ])
    _register("rooke", [
        Ability("rooke_p1", "rooke", "passive", 1, "Safe Hands",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("rooke_s1", "rooke", "skill", 1, "Point-Blank Save",
            "Erases any shot with no roll.",
            auto="stop", when=lambda c: c["action"] == "shoot"),
        Ability("rooke_s2", "rooke", "skill", 3, "Penalty Read",
            "Erases any penalty with no roll.",
            auto="stop", when=lambda c: c["action"] == "penalty"),
    ])
    _register("sachs", [
        Ability("sachs_p1", "sachs", "passive", 1, "Tactical Foul",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("sachs_s1", "sachs", "skill", 1, "Denial",
            "Erases the opponent's action with no roll.",
            auto="stop"),
        Ability("sachs_s2", "sachs", "skill", 3, "Recovery",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("saramadara", [
        Ability("saramadara_p1", "saramadara", "passive", 1, "Quiet Influence",
            "+1 Pass at all times.",
            att=lambda c: 1 if c["action"] == "pass" else 0),
        Ability("saramadara_s1", "saramadara", "skill", 1, "Simple Ball",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("saramadara_s2", "saramadara", "skill", 3, "Late Run",
            "+1 Shot in the final third.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_SHOOT else 0),
    ])
    _register("sendo", [
        Ability("sendo_p1", "sendo", "passive", 1, "Wing Play",
            "+1 Dribble in the final third.",
            att=lambda c: 1 if c["action"] == "dribble" and c["zone"] >= ZONE_SHOOT else 0),
        Ability("sendo_s1", "sendo", "skill", 1, "Wing Cross",
            "Completed pass gives the receiver +2 next action.",
            pass_buff=2),
        Ability("sendo_s2", "sendo", "skill", 3, "Diving Header",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("shiguma", [
        Ability("shiguma_p1", "shiguma", "passive", 1, "Discipline",
            "+1 defense at all times.",
            dfd=lambda c: 1),
        Ability("shiguma_s1", "shiguma", "skill", 1, "Block",
            "Erases any shot with no roll.",
            auto="stop", when=lambda c: c["action"] == "shoot"),
        Ability("shiguma_s2", "shiguma", "skill", 3, "Stand Tackle",
            "Erases the opponent's action with no roll.",
            auto="stop"),
    ])
    _register("silva", [
        Ability("silva_p1", "silva", "passive", 1, "Box Predator",
            "+2 Shot inside the box.",
            att=lambda c: 2 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
        Ability("silva_s1", "silva", "skill", 1, "Power Shot",
            "Keeper −3 on his shot.",
            gk_down=3, when=lambda c: c["action"] == "shoot"),
        Ability("silva_s2", "silva", "skill", 3, "Bulldozing Run",
            "Wins the duel outright and lands one zone forward.",
            auto="win", zone_extra=1),
    ])
    _register("snuffy", [
        Ability("snuffy_p1", "snuffy", "passive", 1, "Tactical Grip",
            "Completed passes give receivers +2; +1 defense.",
            pass_buff=2, dfd=lambda c: 1),
        Ability("snuffy_s1", "snuffy", "skill", 1, "Orchestrated Play",
            "Pass can't be intercepted; receiver lands two zones forward.",
            pass_advance=2),
        Ability("snuffy_s2", "snuffy", "skill", 3, "Desperation Tactic",
            "First lost duel of the match doesn't count.",
            first_free=True),
    ])
    _register("tanaka", [
        Ability("tanaka_p1", "tanaka", "passive", 1, "Set-Piece Duty",
            "+2 on free kicks.",
            att=lambda c: 2 if c["action"] == "freekick" else 0),
        Ability("tanaka_s1", "tanaka", "skill", 1, "Driven Free Kick",
            "Keeper −2 on his free kick.",
            gk_down=2, when=lambda c: c["action"] == "freekick"),
        Ability("tanaka_s2", "tanaka", "skill", 3, "Flat Shot",
            "Shot scores even if the keeper beats him by 2.",
            save_margin=2, when=lambda c: c["action"] == "shoot"),
    ])
    _register("tsunzaki", [
        Ability("tsunzaki_p1", "tsunzaki", "passive", 1, "Link-Up",
            "+1 Pass at all times.",
            att=lambda c: 1 if c["action"] == "pass" else 0),
        Ability("tsunzaki_s1", "tsunzaki", "skill", 1, "One-Two",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("tsunzaki_s2", "tsunzaki", "skill", 3, "Late Arrival",
            "+1 Shot inside the box.",
            att=lambda c: 1 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
    ])
    _register("umaru", [
        Ability("umaru_p1", "umaru", "passive", 1, "Straightline Speed",
            "+1 Dribble at all times.",
            att=lambda c: 1 if c["action"] == "dribble" else 0),
        Ability("umaru_s1", "umaru", "skill", 1, "Sprint Dribble",
            "Beats his marker with no roll and lands one zone forward.",
            auto="win", zone_extra=1, when=lambda c: c["action"] == "dribble"),
        Ability("umaru_s2", "umaru", "skill", 3, "Famished Finish",
            "+2 Shot inside the box.",
            att=lambda c: 2 if c["action"] == "shoot" and c["zone"] >= ZONE_BOX else 0),
    ])
    _register("uraziz", [
        Ability("uraziz_p1", "uraziz", "passive", 1, "Utility Mind",
            "+1 to all duels at all times.",
            att=lambda c: 1),
        Ability("uraziz_s1", "uraziz", "skill", 1, "Any Position",
            "+2 defense while losing.",
            dfd=lambda c: 2 if c["diff"] < 0 else 0),
        Ability("uraziz_s2", "uraziz", "skill", 3, "Surprise Move",
            "Wins the duel outright with no roll.",
            auto="win"),
    ])
    _register("wanima", [
        Ability("wanima_p1", "wanima", "passive", 1, "Twin Sync",
            "+1 to all duels when a twin is on his team.",
            att=lambda c: 1 if _mate("wanima_a", "wanima_j")(c) else 0),
        Ability("wanima_s1", "wanima", "skill", 1, "Twin Give-and-Go",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("wanima_s2", "wanima", "skill", 3, "Double Team Read",
            "+2 defense against dribbles.",
            dfd=lambda c: 2 if c["action"] == "dribble" else 0),
    ])
    _register("yuzu", [
        Ability("yuzu_p1", "yuzu", "passive", 1, "Steady Hand",
            "+1 to all duels at all times.",
            att=lambda c: 1),
        Ability("yuzu_s1", "yuzu", "skill", 1, "Reliable Pass",
            "Pass can't be intercepted; receiver lands one zone forward.",
            pass_advance=1),
        Ability("yuzu_s2", "yuzu", "skill", 3, "Composed Finish",
            "Keeper −2 on his shot.",
            gk_down=2, when=lambda c: c["action"] == "shoot"),
    ])
