"""One Bound passive per roster character (88) — the uniform team-bond layer.

Every entry: id f"{char}_bp", tier 1, bound=True. Activation is handled by
engine.bound_active() (partner on the same team; BOUND_ENABLED gates the whole
system for the test season). Numeric effects scale +(tier - 1) via bound_bonus.

Desc style: pure mechanics — condition first, effect as a stat bullet.
"""

from .abilities import BY_CHAR, REGISTRY, STARTERS, Ability

# (display name, effect kind) — kinds: ad = +1/+1, a = attack, d = defense,
# ad2 = +2/+2 for the three ace pairs (rin, kaiser, loki).
_PAIRS: dict[str, tuple[str, str]] = {
    "achanpong": ("Playmaker's Link", "ad"),
    "agi": ("Midfield Engine", "a"),
    "aiku": ("Libero Lock", "d"),
    "arthur": ("Utility Bond", "ad"),
    "aryu": ("Beauty's Bond", "ad"),
    "bachira": ("Monster Echo", "ad"),
    "barou": ("Royal Decree", "a"),
    "bats": ("Rapid Link", "ad"),
    "birkenstock": ("Concrete Wall", "d"),
    "blake": ("Power Pact", "a"),
    "bos": ("Utility Sync", "ad"),
    "camus": ("Forward's Instinct", "a"),
    "cavasoz": ("Deadball Vow", "a"),
    "chapa": ("Backline Vow", "d"),
    "charles": ("Royal Chamber", "a"),
    "chevalier": ("Playmaker's Vision", "ad"),
    "chigiri": ("Blazing Flank", "ad"),
    "childs": ("Sprint Bond", "a"),
    "cho": ("Team's Pulse", "ad"),
    "delon": ("Line Holder", "d"),
    "endoji": ("Composed Link", "ad"),
    "fukaku": ("Keeper's Vow", "d"),
    "gabin": ("Positional Bond", "d"),
    "gagamaru": ("Beast Wall", "d"),
    "gesner": ("Engine Link", "ad"),
    "gomez": ("Endless Run", "ad"),
    "goodman": ("Last-Man Vow", "d"),
    "hermes": ("Mirror Bond", "d"),
    "hiiragi": ("Finisher's Eye", "a"),
    "hiori": ("Shared Vision", "ad"),
    "hugo": ("Box-to-Box Bond", "ad"),
    "hyoma_k": ("Support Link", "ad"),
    "iemon": ("Anchor Vow", "d"),
    "igaguri": ("Tryhard Pact", "a"),
    "igarashi": ("Hustle Pact", "a"),
    "iglesias": ("Rabbit Dash", "a"),
    "isagi": ("Chemical Reaction", "ad"),
    "ishikari": ("Frame Vow", "d"),
    "kaiser": ("Emperor's Decree", "ad2"),
    "karasu": ("Crow's Read", "d"),
    "kira": ("Star's Vow", "a"),
    "kiyora": ("Ice Link", "ad"),
    "knight": ("Prodigy Pact", "a"),
    "kunigami": ("Righteous Bond", "a"),
    "kurona": ("Apprentice Link", "d"),
    "kuso": ("Tempo Bond", "ad"),
    "lara": ("Poacher's Vow", "a"),
    "lavinho": ("Magic Sync", "ad"),
    "leyden": ("Deep Link", "ad"),
    "loki": ("Godspeed Pact", "ad2"),
    "lorenzo": ("Grave Vow", "d"),
    "luna": ("Lunar Sync", "ad"),
    "nagi": ("Dormant Spark", "ad"),
    "nanase": ("Rainbow Link", "ad"),
    "naruhaya": ("Pressing Bond", "a"),
    "ness": ("Emperor's Shadow", "d"),
    "niang": ("Wing Sync", "ad"),
    "niko": ("Anchor's Vow", "d"),
    "nio": ("Holding Vow", "d"),
    "nishioka": ("Grit Link", "ad"),
    "noa": ("Strongest Bond", "ad"),
    "otoya": ("Shadow Link", "ad"),
    "prince": ("Physique Pact", "a"),
    "raichi": ("Rage Pact", "a"),
    "renoir": ("Safe Hands Vow", "d"),
    "reo": ("Perfect Sync", "ad"),
    "rin": ("Rival's Gaze", "ad2"),
    "rooke": ("Keeper's Hands", "d"),
    "sachs": ("Tactical Vow", "d"),
    "sae": ("Orchestra of Two", "ad"),
    "saramadara": ("Quiet Link", "ad"),
    "sendo": ("Wing Vow", "a"),
    "shidou": ("Devil's Pact", "ad"),
    "shiguma": ("Discipline Vow", "d"),
    "silva": ("Striker's Vow", "a"),
    "snuffy": ("Tactician's Web", "ad"),
    "tanaka": ("Set-Piece Vow", "a"),
    "tokimitsu": ("Unchained Vow", "d"),
    "tsunzaki": ("Link-Up Bond", "ad"),
    "umaru": ("Speed Vow", "a"),
    "uraziz": ("Utility Sync", "ad"),
    "wanima": ("Twin Bond", "ad"),
    "wanima_a": ("Twin One Bond", "ad"),
    "wanima_j": ("Twin Two Bond", "ad"),
    "yuki": ("Quiet Bond", "d"),
    "yukimiya": ("Rhythm Sync", "ad"),
    "yuzu": ("Steady Bond", "ad"),
    "zantetsu": ("Blade Dash", "a"),
}

_EFFECT = {
    "ad": (lambda c: 1, lambda c: 1, "+1 attack and +1 defense."),
    "a": (lambda c: 1, None, "+1 attack."),
    "d": (None, lambda c: 1, "+1 defense."),
    "ad2": (lambda c: 2, lambda c: 2, "+2 attack and +2 defense."),
}


def register_extras() -> None:
    for char, (name, kind) in _PAIRS.items():
        att, dfd, eff = _EFFECT[kind]
        ab = Ability(
            f"{char}_bp", char, "passive", 1, name,
            f"Bound partner on the same team: {eff}",
            att=att, dfd=dfd, bound=True,
        )
        REGISTRY[ab.id] = ab
        kit = BY_CHAR.setdefault(char, [])
        known = {a.id for a in kit}
        if ab.id not in known:
            kit.append(ab)
        # tier-1 → starters, but only APPEND: never clobber an existing list
        # (most chars already have their starter kit registered).
        st = STARTERS.setdefault(char, [])
        if ab.id not in st:
            st.append(ab.id)
