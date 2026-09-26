import json
import sqlite3
import threading
import time

from .config import DB_PATH, SEASON

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    display     TEXT,
    yen         INTEGER NOT NULL DEFAULT 0,
    xp          INTEGER NOT NULL DEFAULT 0,
    title       TEXT,
    joined_at   INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username ON players(username) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_players_display  ON players(display)  WHERE display  IS NOT NULL;

CREATE TABLE IF NOT EXISTS owned (
    char_key   TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES players(user_id),
    boosts     TEXT NOT NULL DEFAULT '{}',
    pulled_at  INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_owned_user ON owned(user_id);

CREATE TABLE IF NOT EXISTS pending_yen (
    username  TEXT PRIMARY KEY,
    amount    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER,
    mode        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    status      TEXT NOT NULL,
    season      INTEGER NOT NULL,
    score1      INTEGER NOT NULL DEFAULT 0,
    score2      INTEGER NOT NULL DEFAULT 0,
    turn        INTEGER NOT NULL DEFAULT 0,
    holder      INTEGER,
    phase       TEXT NOT NULL DEFAULT 'lobby',
    pending     TEXT NOT NULL DEFAULT '{}',
    created_at  INTEGER NOT NULL,
    ended_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_matches_chat ON matches(chat_id, status);

CREATE TABLE IF NOT EXISTS match_players (
    match_id  INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    slot      INTEGER NOT NULL,
    user_id   INTEGER,
    name      TEXT NOT NULL,
    char_key  TEXT,
    team      INTEGER NOT NULL,
    goals     INTEGER NOT NULL DEFAULT 0,
    assists   INTEGER NOT NULL DEFAULT 0,
    actions   INTEGER NOT NULL DEFAULT 0,
    stops     INTEGER NOT NULL DEFAULT 0,
    stats     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (match_id, slot)
);
CREATE INDEX IF NOT EXISTS idx_mp_user ON match_players(user_id);

CREATE TABLE IF NOT EXISTS match_views (
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    PRIMARY KEY (match_id, chat_id)
);

CREATE TABLE IF NOT EXISTS events (
    match_id  INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    seq       INTEGER NOT NULL,
    text      TEXT NOT NULL,
    PRIMARY KEY (match_id, seq)
);

CREATE TABLE IF NOT EXISTS unlocks (
    user_id   INTEGER NOT NULL REFERENCES players(user_id),
    ability   TEXT NOT NULL,
    bought_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, ability)
);

CREATE TABLE IF NOT EXISTS ability_catalog (
    id       TEXT PRIMARY KEY,
    char     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    tier     INTEGER NOT NULL,
    category TEXT NOT NULL,
    name     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_char ON ability_catalog(char, tier);
CREATE INDEX IF NOT EXISTS idx_catalog_cat  ON ability_catalog(category);

CREATE TABLE IF NOT EXISTS wallet_tx (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_user ON wallet_tx(user_id, id DESC);

CREATE TABLE IF NOT EXISTS daily (
    user_id    INTEGER PRIMARY KEY REFERENCES players(user_id),
    streak     INTEGER NOT NULL DEFAULT 0,
    last_day   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quest_progress (
    user_id    INTEGER PRIMARY KEY REFERENCES players(user_id),
    day        INTEGER NOT NULL DEFAULT 0,
    claimed    TEXT NOT NULL DEFAULT '[]',
    progress   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS achievements (
    user_id    INTEGER NOT NULL REFERENCES players(user_id),
    medal      TEXT NOT NULL,
    earned_at  INTEGER NOT NULL,
    PRIMARY KEY (user_id, medal)
);
"""


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
            cols = {r[1] for r in _conn.execute("PRAGMA table_info(matches)")}
            if "starter_id" not in cols:
                _conn.execute("ALTER TABLE matches ADD COLUMN starter_id INTEGER")
            pcols = {r[1] for r in _conn.execute("PRAGMA table_info(players)")}
            if "celebration" not in pcols:
                _conn.execute("ALTER TABLE players ADD COLUMN celebration TEXT")
            _conn.commit()
        return _conn


class tx:
    def __enter__(self) -> sqlite3.Connection:
        _lock.acquire()
        self.conn = connect()
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            _lock.release()
        return False


def now() -> int:
    return int(time.time())


def q(sql: str, params=()) -> list[sqlite3.Row]:
    with tx() as c:
        return c.execute(sql, params).fetchall()


def q1(sql: str, params=()) -> sqlite3.Row | None:
    with tx() as c:
        return c.execute(sql, params).fetchone()


def touch_player(user_id: int, username: str | None) -> None:
    uname = username.lower() if username else None
    with tx() as c:
        if uname:
            c.execute("UPDATE players SET username=NULL WHERE username=? AND user_id<>?", (uname, user_id))
        row = c.execute("SELECT username FROM players WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO players(user_id, username, joined_at) VALUES(?,?,?)",
                (user_id, uname, now()),
            )
        elif row["username"] != uname:
            c.execute("UPDATE players SET username=? WHERE user_id=?", (uname, user_id))

        if uname:
            pend = c.execute("SELECT amount FROM pending_yen WHERE username=?", (uname,)).fetchone()
            if pend and pend["amount"]:
                c.execute("UPDATE players SET yen = yen + ? WHERE user_id=?", (pend["amount"], user_id))
                c.execute(
                    "INSERT INTO wallet_tx(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
                    (user_id, pend["amount"], "آزادسازی ین معلق", now()),
                )
            c.execute("DELETE FROM pending_yen WHERE username=?", (uname,))


def player(user_id: int) -> sqlite3.Row | None:
    return q1("SELECT * FROM players WHERE user_id=?", (user_id,))


def set_celebration(user_id: int, text: str) -> None:
    with tx() as c:
        c.execute("UPDATE players SET celebration=? WHERE user_id=?", (text, user_id))


def find_player(needle: str) -> sqlite3.Row | None:
    key = needle.strip().lstrip("@").lower()
    if not key:
        return None
    return q1(
        "SELECT * FROM players WHERE username=? OR lower(display)=? LIMIT 1",
        (key, key),
    )


def set_display(user_id: int, name: str) -> bool:
    with tx() as c:
        clash = c.execute(
            "SELECT user_id FROM players WHERE lower(display)=? AND user_id<>?",
            (name.lower(), user_id),
        ).fetchone()
        if clash:
            return False
        c.execute("UPDATE players SET display=? WHERE user_id=?", (name, user_id))
        return True


def add_yen(user_id: int, amount: int, reason: str) -> int:
    with tx() as c:
        c.execute("UPDATE players SET yen = yen + ? WHERE user_id=?", (amount, user_id))
        c.execute(
            "INSERT INTO wallet_tx(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
            (user_id, amount, reason, now()),
        )
        row = c.execute("SELECT yen FROM players WHERE user_id=?", (user_id,)).fetchone()
        return row["yen"] if row else 0


def spend_yen(user_id: int, amount: int, reason: str) -> bool:
    with tx() as c:
        row = c.execute("SELECT yen FROM players WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["yen"] < amount:
            return False
        c.execute("UPDATE players SET yen = yen - ? WHERE user_id=?", (amount, user_id))
        c.execute(
            "INSERT INTO wallet_tx(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
            (user_id, -amount, reason, now()),
        )
        return True


def add_pending_yen(username: str, amount: int) -> int:
    uname = username.lower()
    with tx() as c:
        c.execute(
            "INSERT INTO pending_yen(username, amount) VALUES(?,?) "
            "ON CONFLICT(username) DO UPDATE SET amount = amount + excluded.amount",
            (uname, amount),
        )
        return c.execute("SELECT amount FROM pending_yen WHERE username=?", (uname,)).fetchone()["amount"]


def add_xp(user_id: int, amount: int) -> None:
    with tx() as c:
        c.execute("UPDATE players SET xp = xp + ? WHERE user_id=?", (amount, user_id))


def set_xp(user_id: int, value: int) -> None:
    with tx() as c:
        c.execute("UPDATE players SET xp=? WHERE user_id=?", (max(0, value), user_id))


def owned_by(user_id: int) -> sqlite3.Row | None:
    return q1("SELECT * FROM owned WHERE user_id=?", (user_id,))


def taken_keys() -> set[str]:
    return {r["char_key"] for r in q("SELECT char_key FROM owned")}


def assign_char(user_id: int, char_key: str) -> None:
    with tx() as c:
        c.execute("DELETE FROM owned WHERE user_id=?", (user_id,))
        c.execute(
            "INSERT INTO owned(char_key, user_id, boosts, pulled_at) VALUES(?,?,?,?)",
            (char_key, user_id, "{}", now()),
        )


def bump_boost(user_id: int, stat: str, amount: int = 1) -> dict:
    with tx() as c:
        row = c.execute("SELECT char_key, boosts FROM owned WHERE user_id=?", (user_id,)).fetchone()
        boosts = json.loads(row["boosts"])
        boosts[stat] = boosts.get(stat, 0) + amount
        c.execute("UPDATE owned SET boosts=? WHERE char_key=?", (json.dumps(boosts), row["char_key"]))
        return boosts


def set_boosts(user_id: int, boosts: dict) -> None:
    with tx() as c:
        c.execute("UPDATE owned SET boosts=? WHERE user_id=?", (json.dumps(boosts), user_id))


def force_release_char(user_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM owned WHERE user_id=?", (user_id,))


def delete_player(user_id: int) -> bool:
    with tx() as c:
        if c.execute("SELECT 1 FROM players WHERE user_id=?", (user_id,)).fetchone() is None:
            return False
        live = c.execute(
            "SELECT m.id FROM matches m JOIN match_players mp ON mp.match_id = m.id "
            "WHERE mp.user_id=? AND m.status IN ('open','live')",
            (user_id,),
        ).fetchall()
        for row in live:
            c.execute("DELETE FROM match_players WHERE match_id=? AND user_id=?", (row["id"], user_id))
            c.execute("DELETE FROM match_views WHERE match_id=?", (row["id"],))
            c.execute("DELETE FROM events WHERE match_id=?", (row["id"],))
            c.execute("DELETE FROM matches WHERE id=?", (row["id"],))
        c.execute("DELETE FROM owned WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM unlocks WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM wallet_tx WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM players WHERE user_id=?", (user_id,))
        return True


def force_assign_char(user_id: int, char_key: str) -> None:
    with tx() as c:
        c.execute("DELETE FROM owned WHERE user_id=?", (user_id,))
        c.execute(
            "INSERT OR IGNORE INTO owned(char_key, user_id, boosts, pulled_at) VALUES(?,?,?,?)",
            (char_key, user_id, "{}", now()),
        )


def grant_all_unlocks(user_id: int, char_key: str) -> int:
    from . import abilities as _ab
    n = 0
    with tx() as c:
        for ab in _ab.kit_for_char(char_key):
            if ab.tier > 1:
                cur = c.execute(
                    "INSERT OR IGNORE INTO unlocks(user_id, ability, bought_at) VALUES(?,?,?)",
                    (user_id, ab.id, now()),
                )
                n += cur.rowcount
    return n


def revoke_unlock(user_id: int, ability: str) -> bool:
    with tx() as c:
        cur = c.execute("DELETE FROM unlocks WHERE user_id=? AND ability=?", (user_id, ability))
        return cur.rowcount == 1


def players_page(offset: int, limit: int, needle: str | None = None) -> list[sqlite3.Row]:
    if needle:
        like = f"%{needle.lower()}%"
        return q(
            "SELECT * FROM players WHERE lower(COALESCE(display,'')) LIKE ? "
            "OR lower(COALESCE(username,'')) LIKE ? ORDER BY xp DESC LIMIT ? OFFSET ?",
            (like, like, limit, offset),
        )
    return q("SELECT * FROM players ORDER BY xp DESC LIMIT ? OFFSET ?", (limit, offset))


def count_players() -> int:
    return q1("SELECT COUNT(*) AS n FROM players")["n"]


def stat_summary() -> sqlite3.Row:
    return q1(
        "SELECT COUNT(*) AS players, COALESCE(SUM(p.yen),0) AS yen, "
        "(SELECT COUNT(*) FROM owned) AS chars, "
        "(SELECT COUNT(*) FROM matches WHERE status='live') AS live, "
        "(SELECT COUNT(*) FROM matches WHERE status='open') AS open, "
        "(SELECT COUNT(*) FROM matches) AS matches_total, "
        "(SELECT COUNT(*) FROM unlocks) AS unlocks, "
        "(SELECT COALESCE(SUM(amount),0) FROM wallet_tx) AS tx_sum "
        "FROM players p"
    )


def set_title(user_id: int, title: str | None) -> None:
    with tx() as c:
        c.execute("UPDATE players SET title=? WHERE user_id=?", (title, user_id))


def unlocked_ids(user_id: int) -> set[str]:
    return {r["ability"] for r in q("SELECT ability FROM unlocks WHERE user_id=?", (user_id,))}


def grant_unlock(user_id: int, ability: str) -> bool:
    with tx() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO unlocks(user_id, ability, bought_at) VALUES(?,?,?)",
            (user_id, ability, now()),
        )
        return cur.rowcount == 1


def buy_unlock(user_id: int, ability: str, cost: int, reason: str) -> bool:
    with tx() as c:
        row = c.execute("SELECT yen FROM players WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["yen"] < cost:
            return False
        cur = c.execute(
            "INSERT OR IGNORE INTO unlocks(user_id, ability, bought_at) VALUES(?,?,?)",
            (user_id, ability, now()),
        )
        if cur.rowcount != 1:
            return False
        c.execute("UPDATE players SET yen = yen - ? WHERE user_id=?", (cost, user_id))
        c.execute(
            "INSERT INTO wallet_tx(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
            (user_id, -cost, reason, now()),
        )
        return True


def create_match(chat_id: int, mode: str, size: int, starter_id: int | None = None) -> int:
    with tx() as c:
        cur = c.execute(
            "INSERT INTO matches(chat_id, mode, size, status, season, phase, starter_id, created_at) "
            "VALUES(?,?,?,'open',?,'lobby',?,?)",
            (chat_id, mode, size, SEASON, starter_id, now()),
        )
        return cur.lastrowid


def match(match_id: int) -> sqlite3.Row | None:
    return q1("SELECT * FROM matches WHERE id=?", (match_id,))


def live_duel_in(chat_id: int) -> sqlite3.Row | None:
    return q1(
        "SELECT m.* FROM matches m LEFT JOIN match_views v ON v.match_id = m.id "
        "WHERE m.status='live' AND m.phase='duel' AND (m.chat_id=? OR v.chat_id=?) "
        "ORDER BY m.id DESC LIMIT 1",
        (chat_id, chat_id),
    )


def match_of_user(user_id: int) -> sqlite3.Row | None:
    return q1(
        "SELECT m.* FROM matches m JOIN match_players mp ON mp.match_id = m.id "
        "WHERE mp.user_id=? AND m.status IN ('open','live') ORDER BY m.id DESC LIMIT 1",
        (user_id,),
    )


def add_view(match_id: int, chat_id: int, message_id: int) -> None:
    with tx() as c:
        c.execute(
            "INSERT INTO match_views(match_id, chat_id, message_id) VALUES(?,?,?) "
            "ON CONFLICT(match_id, chat_id) DO UPDATE SET message_id = excluded.message_id",
            (match_id, chat_id, message_id),
        )


def views_of(match_id: int) -> list[sqlite3.Row]:
    return q("SELECT chat_id, message_id FROM match_views WHERE match_id=?", (match_id,))


def drop_view(match_id: int, chat_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM match_views WHERE match_id=? AND chat_id=?", (match_id, chat_id))


def roster(match_id: int) -> list[sqlite3.Row]:
    return q("SELECT * FROM match_players WHERE match_id=? ORDER BY team, slot", (match_id,))


def join_match(match_id: int, team: int, user_id: int, name: str, char_key: str | None, stats: dict) -> str:
    with tx() as c:
        m = c.execute("SELECT size, status FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m or m["status"] != "open":
            return "closed"
        if c.execute(
            "SELECT 1 FROM match_players WHERE match_id=? AND user_id=?", (match_id, user_id)
        ).fetchone():
            return "already"
        filled = c.execute(
            "SELECT COUNT(*) AS n FROM match_players WHERE match_id=? AND team=?", (match_id, team)
        ).fetchone()["n"]
        if filled >= m["size"]:
            return "full"
        slot = c.execute(
            "SELECT COALESCE(MAX(slot), 0) AS m FROM match_players WHERE match_id=?", (match_id,)
        ).fetchone()["m"] + 1
        c.execute(
            "INSERT INTO match_players(match_id, slot, user_id, name, char_key, team, stats) VALUES(?,?,?,?,?,?,?)",
            (match_id, slot, user_id, name, char_key, team, json.dumps(stats)),
        )
        return "ok"


def claim_turn(match_id: int, turn: int, holder_slot: int) -> bool:
    with tx() as c:
        cur = c.execute(
            "UPDATE matches SET phase='opening' WHERE id=? AND turn=? AND holder=? "
            "AND status='live' AND phase='play'",
            (match_id, turn, holder_slot),
        )
        return cur.rowcount == 1


def claim_walk(match_id: int, turn: int, holder_slot: int) -> bool:
    """Advance claims the turn (bump + lock phase) so no other action can play it."""
    with tx() as c:
        cur = c.execute(
            "UPDATE matches SET turn = turn + 1, phase='opening' WHERE id=? AND turn=? AND holder=? "
            "AND status='live' AND phase='play'",
            (match_id, turn, holder_slot),
        )
        return cur.rowcount == 1


def release_turn(match_id: int) -> None:
    with tx() as c:
        c.execute("UPDATE matches SET phase='play' WHERE id=? AND phase='opening'", (match_id,))


def kickoff(match_id: int) -> bool:
    with tx() as c:
        m = c.execute("SELECT size, status FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m or m["status"] != "open":
            return False
        counts = c.execute(
            "SELECT team, COUNT(*) AS n FROM match_players WHERE match_id=? GROUP BY team",
            (match_id,),
        ).fetchall()
        tally = {r["team"]: r["n"] for r in counts}
        if tally.get(1, 0) != m["size"] or tally.get(2, 0) != m["size"]:
            return False
        c.execute("UPDATE matches SET status='live' WHERE id=?", (match_id,))
        return True


def leave_match(match_id: int, user_id: int) -> bool:
    """Only open lobbies accept quits — live/done matches are untouchable."""
    with tx() as c:
        m = c.execute("SELECT status FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m or m["status"] != "open":
            return False
        c.execute("DELETE FROM match_players WHERE match_id=? AND user_id=?", (match_id, user_id))
        return True


def update_match(match_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE matches SET {cols} WHERE id=?", (*fields.values(), match_id))


def bump_slot(match_id: int, slot: int, **fields) -> None:
    cols = ", ".join(f"{k} = {k} + ?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE match_players SET {cols} WHERE match_id=? AND slot=?", (*fields.values(), match_id, slot))


def log_event(match_id: int, text: str) -> None:
    with tx() as c:
        row = c.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE match_id=?", (match_id,)).fetchone()
        c.execute("INSERT INTO events(match_id, seq, text) VALUES(?,?,?)", (match_id, row["m"] + 1, text))


def recent_events(match_id: int, limit: int) -> list[str]:
    rows = q("SELECT text FROM events WHERE match_id=? ORDER BY seq DESC LIMIT ?", (match_id, limit))
    return [r["text"] for r in reversed(rows)]


def last_kickoff_team(chat_id: int) -> int | None:
    """Team of the most recent kickoff in this chat — used to alternate kickoffs."""
    row = q1(
        "SELECT e.text FROM events e JOIN matches m ON m.id = e.match_id "
        "WHERE m.chat_id = ? AND (e.text LIKE '%kickoff:blue%' OR e.text LIKE '%kickoff:red%') "
        "ORDER BY e.match_id DESC, e.seq DESC LIMIT 1",
        (chat_id,),
    )
    if row is None:
        return None
    if "kickoff:blue" in row["text"]:
        return 1
    return 2


def open_matches(chat_id: int | None = None) -> list[sqlite3.Row]:
    if chat_id is None:
        return q("SELECT * FROM matches WHERE status IN ('open','live') ORDER BY id DESC LIMIT 20")
    return q("SELECT * FROM matches WHERE chat_id=? AND status IN ('open','live') ORDER BY id DESC", (chat_id,))


def career(user_id: int) -> sqlite3.Row:
    return q1(
        "SELECT COUNT(*) AS played, COALESCE(SUM(goals),0) AS goals, COALESCE(SUM(assists),0) AS assists, "
        "COALESCE(SUM(stops),0) AS stops "
        "FROM match_players mp JOIN matches m ON m.id = mp.match_id "
        "WHERE mp.user_id=? AND m.status='done'",
        (user_id,),
    )


def record(user_id: int) -> tuple[int, int, int]:
    rows = q(
        "SELECT mp.team, m.score1, m.score2 FROM match_players mp JOIN matches m ON m.id = mp.match_id "
        "WHERE mp.user_id=? AND m.status='done'",
        (user_id,),
    )
    w = d = l = 0
    for r in rows:
        mine, theirs = (r["score1"], r["score2"]) if r["team"] == 1 else (r["score2"], r["score1"])
        if mine > theirs:
            w += 1
        elif mine == theirs:
            d += 1
        else:
            l += 1
    return w, d, l


def leaderboard(field: str, limit: int = 10) -> list[sqlite3.Row]:
    if field == "yen":
        return q(
            "SELECT user_id, username, display, yen AS value FROM players "
            "WHERE yen > 0 ORDER BY yen DESC LIMIT ?",
            (limit,),
        )
    if field == "level":
        return q(
            "SELECT user_id, username, display, xp AS value FROM players "
            "WHERE xp > 0 ORDER BY xp DESC LIMIT ?",
            (limit,),
        )
    col = {"goals": "goals", "assists": "assists", "stops": "stops"}[field]
    return q(
        f"SELECT p.user_id, p.username, p.display, SUM(mp.{col}) AS value "
        "FROM match_players mp JOIN matches m ON m.id = mp.match_id "
        "JOIN players p ON p.user_id = mp.user_id "
        "WHERE m.status='done' AND m.season=? "
        "GROUP BY p.user_id HAVING value > 0 ORDER BY value DESC LIMIT ?",
        (SEASON, limit),
    )


def search_players(needle: str, limit: int = 12) -> list[sqlite3.Row]:
    like = f"%{needle.lower()}%"
    if needle:
        return q(
            "SELECT * FROM players WHERE lower(COALESCE(display,'')) LIKE ? "
            "OR lower(COALESCE(username,'')) LIKE ? ORDER BY xp DESC LIMIT ?",
            (like, like, limit),
        )
    return q("SELECT * FROM players ORDER BY xp DESC LIMIT ?", (limit,))


def stale_lobbies(cutoff: int) -> list[sqlite3.Row]:
    return q("SELECT * FROM matches WHERE status='open' AND created_at < ?", (cutoff,))


def matches_page(offset: int, limit: int, statuses: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
    if statuses:
        marks = ",".join("?" for _ in statuses)
        return q(f"SELECT * FROM matches WHERE status IN ({marks}) ORDER BY id DESC LIMIT ? OFFSET ?", (*statuses, limit, offset))
    return q("SELECT * FROM matches ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))


def count_matches(statuses: tuple[str, ...] | None = None) -> int:
    if statuses:
        marks = ",".join("?" for _ in statuses)
        return q1(f"SELECT COUNT(*) AS n FROM matches WHERE status IN ({marks})", statuses)["n"]
    return q1("SELECT COUNT(*) AS n FROM matches")["n"]


# ------------------------------------------------------------------ daily / quests / achievements

def daily_row(user_id: int) -> sqlite3.Row | None:
    return q1("SELECT * FROM daily WHERE user_id=?", (user_id,))


def claim_daily(user_id: int, day: int, streak: int, amount: int, reason: str) -> tuple[int, int, int] | None:
    """Atomically claim the daily reward. Returns (new_yen, streak, last_day) or None if already claimed."""
    with tx() as c:
        row = c.execute("SELECT streak, last_day FROM daily WHERE user_id=?", (user_id,)).fetchone()
        if row and row["last_day"] == day:
            return None
        new_streak = streak
        c.execute(
            "INSERT INTO daily(user_id, streak, last_day) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET streak=?, last_day=?",
            (user_id, new_streak, day, new_streak, day),
        )
        c.execute(
            "INSERT INTO wallet_tx(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
            (user_id, amount, reason, now()),
        )
        c.execute("UPDATE players SET yen = yen + ? WHERE user_id=?", (amount, user_id))
        fresh = c.execute("SELECT yen FROM players WHERE user_id=?", (user_id,)).fetchone()
        return (fresh["yen"] if fresh else 0, new_streak, day)


def quest_row(user_id: int) -> sqlite3.Row | None:
    return q1("SELECT * FROM quest_progress WHERE user_id=?", (user_id,))


def set_quest_state(user_id: int, day: int, progress: dict, claimed: list[str]) -> None:
    with tx() as c:
        c.execute(
            "INSERT INTO quest_progress(user_id, day, claimed, progress) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET day=?, claimed=?, progress=?",
            (user_id, day, json.dumps(claimed), json.dumps(progress),
             day, json.dumps(claimed), json.dumps(progress)),
        )


def season_stats_since(user_id: int, since: int) -> sqlite3.Row:
    return q1(
        "SELECT COUNT(DISTINCT mp.match_id) AS played, COALESCE(SUM(mp.goals),0) AS goals, "
        "COALESCE(SUM(mp.assists),0) AS assists, COALESCE(SUM(mp.stops),0) AS stops, "
        "COALESCE(SUM(mp.actions),0) AS actions "
        "FROM match_players mp JOIN matches m ON m.id = mp.match_id "
        "WHERE mp.user_id=? AND m.status='done' AND m.ended_at>=?",
        (user_id, since),
    )


def achievements_of(user_id: int) -> list[sqlite3.Row]:
    return q("SELECT medal, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at", (user_id,))


def grant_achievement(user_id: int, medal: str) -> bool:
    with tx() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO achievements(user_id, medal, earned_at) VALUES(?,?,?)",
            (user_id, medal, now()),
        )
        return cur.rowcount == 1
