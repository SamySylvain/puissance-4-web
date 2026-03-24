# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Web-based Connect Four (Puissance 4) game on a **9×9 board** (not the classic 7×6). Built with a Python/Flask backend and vanilla JavaScript frontend. Deployed on Render.com.

## Commands

**Install dependencies:**
```
pip install -r requirements.txt
```

**Run the dev server (debug mode, port 5000):**
```
python app.py
```

**Run with gunicorn (production-style, as deployed on Render):**
```
gunicorn app:app
```

The app is accessible at `http://localhost:5000`. There are no automated tests.

## Architecture

### Backend (`app.py`)
Flask app using **server-side session** (cookie-based) to store the entire game state under the key `"game"`. All game logic goes through a single mutable state dict. Key helpers:
- `_new_state(mode)` — creates a fresh game state and registers it in the DB.
- `_play_move(state, colonne)` — applies a human move, checks for victory, syncs DB.
- `_ai_play_once(state)` — runs minimax (or random for mode 4) and applies the AI move.
- `_sync_db(state, statut, gagnants)` — fire-and-forget DB persistence; errors are printed but never raised.
- `_compute_scores(state)` — fills `scores_colonnes` with per-column minimax evaluations shown on the board; only active in modes 2 and 3, capped at depth 3.

REST API endpoints (all JSON):
- `POST /api/new_game` — `{ mode: 1|2|3|4 }`
- `GET  /api/state`
- `POST /api/play` — `{ col: 0-indexed }`
- `POST /api/ai_move` — triggers one AI move (modes 2, 4)
- `POST /api/ai_step` — triggers one step in AI-vs-AI (mode 3)
- `POST /api/undo`
- `POST /api/abandon`
- `POST /api/save` / `POST /api/load` / `POST /api/clear_state`
- `POST /api/set_depth` — `{ depth: 1-6 }`

Game modes: `1` = PvP, `2` = Player vs Minimax AI, `3` = AI vs AI, `4` = Player vs Random AI.

### Game Logic & AI (`modeleGraph.py`)
Self-contained module with no Flask dependency. Key areas:

**Board primitives:** `creerPlateau`, `poserJeton` (returns the row where the token landed, or `False`), `verificationVictoire` (returns the list of winning positions or `None`).

**AI — Minimax with alpha-beta pruning (`minimax`):**
- Move ordering: columns sorted by distance from center (center-first).
- Heuristic (`evaluer_plateau`): positional bonus table cached in `_POS_TABLE_CACHE` + sliding 4-cell window scoring across all four directions.
- `analyser_tous_les_coups` — runs minimax for every legal column to populate the per-column score hints displayed at the bottom of the board.

**Database (optional MySQL):** `mysql.connector` is imported with a `try/except`; all DB functions degrade silently if MySQL is unavailable. The DB tracks:
- `Partie` table: move string (`coups`, 1-indexed columns), game mode, status (`EN_COURS`, `FIN_ROUGE`, `FIN_JAUNE`, `ABANDON`, `SAVE`), `confiance`, `nb_colonnes`, `id_antecedent`/`id_suivant` (lexicographic ordering of games), `id_symetrie` (JSON list of mirror-symmetric game IDs).
- `Situation` table: canonical board hash per game, computed via `obtenir_forme_normale` (stores `min(normal, mirror)` to deduplicate symmetric positions).

`actualiser_coup_db` is called after every move and rebuilds all relational links (antecedent, suivant, symetries) from scratch for the current game.

### Frontend (`templates/`)
Pure vanilla JS, no build step required.

**`index.html`** — Main game view. Renders the board on a `<canvas>` (540×620 px, 60 px per cell). Game state is fetched from the Flask session via the REST API and cached in a JS `state` variable. AI moves are triggered by `setInterval`/`setTimeout` (600 ms delay) and guarded by an `aiRequestInFlight` flag to prevent concurrent requests. Saved games are stored in `localStorage` under the key `puissance4_saves`.

**`saves.html`** — Saved games list. Reads entirely from `localStorage`; loads a save by POSTing its state object to `/api/load` then redirecting to `/`.

### State object shape (session `"game"`)
```
{
  mode: 1|2|3|4,
  nb_lignes: 9, nb_colonnes: 9,
  plateau: [[int]],           // 0=empty, 1=red, 2=yellow
  jeton_actuel: 1|2,
  jeu_en_cours: bool,
  historique: [[row, col]],   // ordered list of moves
  historique_coups: str,      // move string, 1-indexed cols (e.g. "5469")
  pions_gagnants: [[row, col]],
  scores_colonnes: [int|null],
  dernier_score_ia: int,
  profondeur_ia: int,         // 1–6
  id_partie_db: int|null
}
```

## Deployment

`render.yaml` defines a Render.com web service. Build command: `pip install -r requirements.txt`. Start command: `gunicorn app:app`. The `PORT` environment variable is read automatically in `app.py`.

`mysql-connector-python` is **not** in `requirements.txt` (the DB layer is optional). If MySQL features are needed in a deployment, add it manually.
