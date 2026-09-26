# 🧭 BlueLock — Roadmap

Date: 2026-09-01 · Based on a full code read-through (~7,600 lines, 19 files)
Updated: 2026-09-23 — status pass (no design changes, just reality sync).
Updated: 2026-09-25 — passives now arm themselves (skills stay manual), canon stat rebalance,
4 newcomers (Aiku, Charles, Ness, Zantetsu), starter-kit bug fixed for extra-registered characters.
Also 2026-09-25 — Phase 7 goal cinema shipped; Shop v2 (sectioned screen, ≤2-col training grid,
reroll confirm screen, equipped-title marks) + one canonical screen header via `fmt.header`/`fmt.hint`.

**Status: Phases 0–3 SHIPPED (2026-09-07 → 2026-09-08).**
Next up: Phase 7 goal cinema → 5 ELO+leagues → 6 H2H/cups/bets → 4 momentum/tactics → 9 /shootout → 8 economy → 10 season rollover.

---

## 1. What exists today

| File | Role | State |
|---|---|---|
| `bluelock/engine.py` (1,008) | Heart of the game: duels, set pieces, penalties, gambles | Clean, simple state machine |
| `bluelock/abilities.py` + `abilities_extra.py` | 32 characters × 6 abilities = 192 | Dataclass registry, clean |
| `bluelock/db.py` (620) | SQLite + WAL, atomic transactions | Solid |
| `bluelock/views.py` (648) | All renders, keyboards | Phone-first design system works |
| `bluelock/handlers_match.py` | Match flow, real dice, relay | Core UX |
| `bluelock/handlers_admin.py` (1,010) | Full panel with registry | Fine |
| `sim_check.py` (861) | Ability + correctness harness | Real asset |
| `balance_check.py` | Monte Carlo tuning harness | Real asset |

**Treasures not to break:**
- 🎲 Real Telegram dice (cheat-proof, feels physical)
- 👁 Multi-view — matches watchable from any chat (`match_views`)
- 💬 PM→group relay (`relay_chat`)
- 🧪 Test culture: any engine change must pass `sim_check`

---

## 2. Found while reading the code (report only)

1. ~~**Dead wall UI**~~ — gone from the tree before Phase 0 (roadmap finding was stale).
2. ~~**Dead code**~~ — `wall_power` / `WALL_DIVISOR` already removed.
3. ~~**Description ≠ mechanic**~~ — **FIXED 2026-09-23.** The s2 descriptions had been rewritten during the 2026-09-06 sweep, but the mechanics behind them were still broken: pure `tie_win` pass skills (`wanima_*_s2`, `hyoma_k_s2`) never armed/spent and the exact-tie deadlock preempted them; `pass_advance` skills (`hiori_s1`, `sae_s3`, `wanima_*_3`) never granted their promised interception immunity and never spent their charge (infinite zone jumps). Engine now implements all of it — covered by targeted `sim_check` tests.
4. ~~**Code smell**~~ — `is_pm` hasattr line and dead loop already gone.
5. ~~**Environment hygiene**~~ — git repo + `.gitignore` + `requirements.txt` since Phase 0; scratch DBs stay gitignored.

---

## 3. Roadmap — 10 phases

Ordered by impact ÷ effort. After each phase, `sim_check` must pass (and `balance_check` if numbers changed).

---

### Phase 0 — Sweep & safety (⏱ half a day) ✅ shipped 2026-09-07

- `git init` + `.gitignore` (`*.db*`, `.venv`, `.env`, `__pycache__`) — before anything else.
- `requirements.txt` (just `pyTelegramBotAPI`).
- Remove the dead code above; sync ability description/mechanic (or actually implement the promised mechanic — Phase 4).
- Move test DBs to `tests/` or clean them up.

---

### Phase 1 — Anti-AFK & match QoL (⏱ 1 day) ✅ shipped 2026-09-07

**Why:** right now if an attacker never rolls their die, the match hangs forever and only an admin can rescue it. For a real group this is the biggest hole.

- **Auto-roll timer:** after N minutes of waiting, the bot rolls a random die for the player + announces "⏱ rolled for X". (Inside `advance` in `handlers_match.py` + a timer job; the `sweep_loop` pattern in `main.py` is ready to reuse.)
- **`/matchlog #ID`** — full match replay. Almost free: the `events` table already stores everything, only the display is missing.
- A "show rules" button on the scoreboard itself.

---

### Phase 2 — Daily heartbeat: streaks & quests (⏱ 2–3 days) ✅ shipped 2026-09-07

**Why:** the economy currently only lives through matches. The Duolingo/Hamster Kombat pattern: daily return + small completable tasks.

- **`/daily`** — daily yen with an escalating streak multiplier (day 1 → day 7), plus a "streak repair" item as a sink.
- **Rotating daily quests (3):** "score 2 goals", "make 3 stops", "play 1 match" — computable from the existing `match_players` tables, no heavy new system needed.
- **Achievements (medals):** hat-trick, first goal, 10 stops in a season, "clutch" (goal in the last 10%), hidden ones. Shown on `/profile`.
- Files: `handlers_player.py` (command), `db.py` (two tables: `daily`, `achievements`), `payouts.py` (event hook).

---

### Phase 3 — FLOW STATE: the ego meter (⏱ 2 days) ✅ shipped 2026-09-07 ⭐ Blue Lock signature
(Shipped as field-duel streak → power-up design with FLOW aura; admin `/alvl` added alongside.)

**Why:** Blue Lock is ego. A meter that makes the moment of brilliance objective — this turns the bot's identity from "dice football" into "actually Blue Lock".

- Every player has a **FLOW 🔥 0–5 meter** per match: +1 on a won duel, a goal, a stop.
- When full, they can spend it before their action: **+3 on this action or a die reroll** — with a dramatic line in chat ("🔥 X goes FLOW!").
- Lives in the match `state` (`engine.fresh_state`) + a button next to the ability bar. No cross-match persistence needed — that's enough.

---

### Phase 4 — Momentum & captain tactics (⏱ 3–4 days) 🟡

**Why:** imported from tabletop football games (Counter Attack / Blood Bowl pattern): gives matches a dramatic wave and makes the captain matter.

- **Momentum meter `−2..+2`:** every successful action pulls momentum toward your team; a goal swings it `±2`; the attack die sums with your side's positive momentum. One line on the scoreboard: `⚡ ▰▱ Blue +1`.
- **Tactics:** the captain picks 1 tactic at kickoff:
  - High press: opponent turnovers restart at zone 1 instead of 0
  - Bus: +1 MET for the back line, −1 shot for their strikers
  - Counter: after winning the ball, one free zone
  - Tiki-taka: consecutive passes +1 cumulative (cap +2) — the existing `chain` hook is there
- ~~While here, turn the Phase 0 ability promises into real mechanics~~ — interception immunity + pass zone advance shipped 2026-09-23 (see finding #3 above).
- Files: `engine.py` (`turnover`, `resolve`), `views.py` (display), `handlers_match.py` (tactic pick).

---

### Phase 5 — Ranked rating & leagues (⏱ 2–3 days) 🟡

**Why:** "Ranked" is currently just the "first to 3" rule; nothing accumulates. A persistent number = a long-term goal.

- **Simple ELO:** one `rating` column on `players`; updated by `payouts.settle` (full-weight ranked, half-weight friendly).
- **`/top rating`** joins the leaderboard.
- **Leagues:** Bronze→Diamond like Hamster Kombat; season-end promotion/relegation + prizes.
- Later: matchmaking — "a player at your level is online: challenge button" (`/challenge @user`).

---

### Phase 6 — Rivalries & cups (⏱ 3 days) 🟡⭐

**Why:** rivalry is the soul of Blue Lock. Isagi has nothing to devour without Rin.

- **H2H record:** table `(user_a, user_b, wins_a, wins_b)`; updated after every match. `/rivalry @user` — "you've beaten them 4 times, lost once". A "devourer" medal for the best H2H record.
- **Cup `/newcup`:** 4/8-player bracket in the group; round 1 auto-creates lobbies; champion gets a title + yen + a celebration post. New `cups` table.
- **Spectator bets:** on any live match, non-players can bet yen on Blue/Red before the final stretch (inline button, winners split the pool). Keeps the group alive during matches — and the multi-view infra is already there.

---

### Phase 7 — Goal cinema (⏱ 1 day) 🟢 cheap, high impact ✅ shipped 2026-09-25

- **Varied commentary lines:** `engine.describe` is one fixed line per outcome; make a pool of 3–4 variants per outcome + anime quotes on big moments (hat-trick, FLOW goal, double gamble).
- **Goal scene:** after a goal, render a goal card (name + duel score + activated skill name) — same visual language as `deliver_card`.
- **Personal celebration:** each player registers their own goal emoji/phrase (`/celebration`) that appears after their goals.
- **Hall of Fame:** `events` already keeps everything; "goal of the season" with reaction voting. *(⏳ later — not in this ship)*

---

### Phase 8 — Economy & collection (⏱ open, week 2+) 🟢

- **Gacha pity:** after N rerolls guarantee an SSR — SSR weight is only 3 of 82 today with no guarantee.
- **Cosmetics:** card frame by rank, shirt number (`/number`), rare titles as economy sinks.
- **Transfer market with fee:** player-to-player with a burned commission (natural sink). Farming risk — bottom of the list.
- Make sure the faucet stays: yen is minted only by matches + daily; everything else is a sink.

---

### Phase 9 — Solo content: keeper shootout (⏱ 1 day) 🟢

**Why:** when friends are offline there's nothing to do right now.

- `/shootout` — a best-of-three penalty mini-game against BlueLock Man (reusing the existing nerve math: pick a corner vs keeper read). 3 shots a day, small yen, its own streak. The code is nearly a clone of the match `penalty` branch.

---

### Phase 10 — Season rollover (⏱ 1 day)

- `SEASON` is hardcoded `1` and never advances today.
- `/anewseason` admin: archive leaderboards (`season_archive` table), pay championship prizes (a real "World Eleven" title), bump the season, farewell/welcome post.
- Ties into Phases 5–6 (leagues and cups want a season end).

---

## 4. Priority matrix

| Phase | Impact | Effort | Order |
|---|---|---|---|
| 0 sweep + git | 🔴 critical | half a day | ✅ shipped |
| 1 anti-AFK + matchlog | 🔴 high | 1 day | ✅ shipped |
| 2 daily/quests | 🔴 high | 2–3 days | ✅ shipped |
| 3 FLOW | 🔴 identity | 2 days | ✅ shipped |
| 7 goal cinema | 🟢 cheap | 1 day | ✅ shipped |
| 5 rating/leagues | 🟡 high | 2–3 days | after 7 |
| 6 H2H/cup/bets | 🟡 high | 3 days | after 5 |
| 4 momentum/tactics | 🟡 medium | 3–4 days | after 6 |
| 9 shootout | 🟢 nice | 1 day | 9 |
| 8 economy | 🟢 long-term | open | 10 |
| 10 season | 🟡 tied | 1 day | with 5–6 |

**Suggested path:** ~~Phase 7 goal cinema~~ ✅ done (2026-09-25) → next: 5–6 (rating + rivalry) → 4 momentum/tactics.

---

## 5. Design principles (keep these)

1. **Real Telegram dice = identity.** Never switch to server-side dice for player rolls.
2. **Every new feature must create either a "moment" or a "return"** — nothing neutral.
3. Before any engine change: `sim_check`; after any numeric tuning: `balance_check`. As already practiced.
4. New numbers (momentum, FLOW, ELO) go into `config.py` as constants first.
