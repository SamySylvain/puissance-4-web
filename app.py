import os
import random
from flask import Flask, jsonify, render_template, request, session

from modeleGraph import (
    analyser_tous_les_coups,
    creerPlateau,
    minimax,
    poserJeton,
    verificationVictoire,
    initialiser_partie_db,
    actualiser_coup_db,
)


app = Flask(__name__)
app.secret_key = "puissance4-web-secret"

NB_LIGNES = 9
NB_COLONNES = 9


def _state_for_response(state):
    payload = dict(state)
    payload["historique"] = [list(c) for c in state["historique"]]
    payload["pions_gagnants"] = [list(c) for c in state["pions_gagnants"]]
    return payload


def _compute_scores(state):
    state["scores_colonnes"] = [None] * NB_COLONNES
    if state["jeu_en_cours"] and state["mode"] in (2, 3):
        profondeur_scores = int(state.get("profondeur_ia", 3))
        profondeur_scores = max(1, min(profondeur_scores, 5))
        scores = analyser_tous_les_coups(
            state["plateau"], profondeur_scores, state["jeton_actuel"], NB_LIGNES, NB_COLONNES
        )
        for col, score in scores.items():
            state["scores_colonnes"][col] = score


def _new_state(mode):
    # Initialise la partie en base de données dès la création
    id_partie_db = initialiser_partie_db(mode, NB_LIGNES, NB_COLONNES)

    state = {
        "mode": mode,
        "nb_lignes": NB_LIGNES,
        "nb_colonnes": NB_COLONNES,
        "plateau": creerPlateau(NB_LIGNES, NB_COLONNES),
        "jeton_actuel": 1,
        "jeu_en_cours": True,
        "historique": [],
        "historique_coups": "",
        "pions_gagnants": [],
        "scores_colonnes": [None] * NB_COLONNES,
        "dernier_score_ia": 0,
        "profondeur_ia": 9,
        "historique_futur": [],
        # --- NOUVEAU : ID de la partie en base de données ---
        "id_partie_db": id_partie_db,
    }
    _compute_scores(state)
    return state


def _play_move(state, colonne):
    if not state["jeu_en_cours"]:
        return False, "Partie terminée"

    if colonne < 0 or colonne >= NB_COLONNES:
        return False, "Colonne invalide"

    ligne_posee = poserJeton(state["plateau"], colonne, state["jeton_actuel"])
    if ligne_posee is False:
        return False, "Colonne pleine"

    state["historique_coups"] += str(colonne + 1)
    state["historique"].append([ligne_posee, colonne])

    resultat = verificationVictoire(state["plateau"], NB_LIGNES, NB_COLONNES)
    if resultat:
        state["pions_gagnants"] = [list(c) for c in resultat]
        state["jeu_en_cours"] = False

        # Statut final : quel joueur a gagné ?
        statut_final = "FIN_ROUGE" if state["jeton_actuel"] == 1 else "FIN_JAUNE"

        # Persistance en BDD avec statut de fin et pions gagnants
        _sync_db(state, statut=statut_final, gagnants=resultat)
    else:
        state["jeton_actuel"] = 2 if state["jeton_actuel"] == 1 else 1

        # Persistance en BDD après chaque coup normal
        _sync_db(state)

    _compute_scores(state)
    return True, None


def _sync_db(state, statut="EN_COURS", gagnants=None):
    """Synchronise l'état courant de la partie avec la base de données.

    Appelle actualiser_coup_db qui met à jour :
      - les coups joués
      - le statut (EN_COURS / FIN_ROUGE / FIN_JAUNE / ABANDON)
      - les pions gagnants
      - les liens antécédent / suivant
      - les symétries
    """
    id_partie = state.get("id_partie_db")
    if id_partie is None:
        return

    try:
        actualiser_coup_db(
            id_partie,
            state["historique_coups"],
            state["plateau"],
            statut,
            gagnants,
        )
    except Exception as e:
        print(f"[DB] Erreur sync partie {id_partie} : {e}")


def _ai_play_once(state):
    if not state["jeu_en_cours"]:
        return

    if state.get("mode") == 4:
        colonnes_possibles = [c for c in range(NB_COLONNES) if state["plateau"][0][c] == 0]
        if not colonnes_possibles:
            state["jeu_en_cours"] = False
            state["scores_colonnes"] = [None] * NB_COLONNES
            return
        col = random.choice(colonnes_possibles)
        _play_move(state, col)
        state["dernier_score_ia"] = 0
        return

    profondeur = int(state.get("profondeur_ia", 3))
    profondeur = max(1, min(profondeur, 9))

    score, col = minimax(
        state["plateau"],
        profondeur,
        True,
        state["jeton_actuel"],
        NB_LIGNES,
        NB_COLONNES,
    )

    if col is not None:
        _play_move(state, col)

    state["dernier_score_ia"] = score


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/saves")
def saves_page():
    return render_template("saves.html")


@app.post("/api/new_game")
def new_game():
    data = request.get_json(silent=True) or {}
    mode = int(data.get("mode", 1))
    if mode not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "Mode invalide"}), 400

    state = _new_state(mode)
    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.get("/api/state")
def get_state():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie en cours"}), 404
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/set_depth")
def set_depth():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    data = request.get_json(silent=True) or {}
    profondeur = int(data.get("depth", 3))
    state["profondeur_ia"] = max(1, min(profondeur, 9))
    _compute_scores(state)
    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/play")
def play():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    data = request.get_json(silent=True) or {}
    colonne = int(data.get("col", -1))

    if state["mode"] in (2, 4) and state["jeton_actuel"] == 2:
        return jsonify({"ok": False, "error": "Tour de l'IA"}), 400

    if state["mode"] == 3:
        return jsonify({"ok": False, "error": "Mode IA vs IA"}), 400

    ok, err = _play_move(state, colonne)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400

    # Nouveau coup joué → on efface l'historique futur (branche alternative abandonnée)
    state["historique_futur"] = []

    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/ai_move")
def ai_move():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    if state["mode"] not in (2, 4):
        return jsonify({"ok": False, "error": "Disponible uniquement en mode Joueur vs IA"}), 400

    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "Partie terminée"}), 400

    if state["jeton_actuel"] != 2:
        return jsonify({"ok": False, "error": "Ce n'est pas le tour de l'IA"}), 400

    _ai_play_once(state)
    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/ai_step")
def ai_step():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    if state["mode"] != 3:
        return jsonify({"ok": False, "error": "Disponible uniquement en mode IA vs IA"}), 400

    if state["jeu_en_cours"]:
        _ai_play_once(state)

    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/undo")
def undo():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    if len(state["historique"]) == 0:
        return jsonify({"ok": False, "error": "Aucun coup à annuler"}), 400

    futur = state.setdefault("historique_futur", [])

    l, c = state["historique"].pop()
    futur.append([l, c])
    # Le joueur qui a posé ce jeton doit rejouer → on lit sa couleur avant d'effacer
    state["jeton_actuel"] = state["plateau"][l][c]
    state["plateau"][l][c] = 0
    if state["historique_coups"]:
        state["historique_coups"] = state["historique_coups"][:-1]

    if state["mode"] == 2 and len(state["historique"]) > 0:
        l, c = state["historique"].pop()
        futur.append([l, c])
        state["jeton_actuel"] = state["plateau"][l][c]
        state["plateau"][l][c] = 0
        if state["historique_coups"]:
            state["historique_coups"] = state["historique_coups"][:-1]

    state["jeu_en_cours"] = True
    state["pions_gagnants"] = []

    # Synchronisation BDD après annulation (statut redevient EN_COURS)
    _sync_db(state, statut="EN_COURS", gagnants=None)

    _compute_scores(state)
    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/redo")
def redo():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    futur = state.setdefault("historique_futur", [])
    if not futur:
        return jsonify({"ok": False, "error": "Rien à rejouer"}), 400

    # En mode 2 on rejoue par paires (coup joueur + coup IA)
    nb = 2 if state["mode"] == 2 and len(futur) >= 2 else 1

    for _ in range(nb):
        if not futur:
            break
        l, c = futur.pop()
        _play_move(state, c)

    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/abandon")
def abandon():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "La partie est déjà terminée"}), 400

    state["jeu_en_cours"] = False
    state["pions_gagnants"] = []
    state["scores_colonnes"] = [None] * NB_COLONNES

    # Statut abandon : on précise quelle couleur abandonne
    statut_abandon = "ABANDON_ROUGE" if state["jeton_actuel"] == 1 else "ABANDON_JAUNE"
    _sync_db(state, statut=statut_abandon, gagnants=None)

    session["game"] = state
    return jsonify({
        "ok": True,
        "state": _state_for_response(state),
        "message": "Partie abandonnée."
    })


@app.post("/api/load")
def load_saved():
    data = request.get_json(silent=True) or {}
    saved_state = data.get("state")
    if not isinstance(saved_state, dict):
        return jsonify({"ok": False, "error": "Données invalides"}), 400

    required_keys = {
        "mode",
        "nb_lignes",
        "nb_colonnes",
        "plateau",
        "jeton_actuel",
        "jeu_en_cours",
        "historique",
        "historique_coups",
        "pions_gagnants",
        "scores_colonnes",
        "dernier_score_ia",
        "profondeur_ia",
    }
    if not required_keys.issubset(saved_state.keys()):
        return jsonify({"ok": False, "error": "Sauvegarde incomplète"}), 400

    session["game"] = saved_state
    return jsonify({"ok": True, "state": _state_for_response(saved_state)})


@app.post("/api/save")
def save_game():
    state = session.get("game")
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "La partie est déjà terminée"}), 400

    # Enregistre le statut SAVE en BDD
    _sync_db(state, statut="SAVE", gagnants=None)

    # On garde la session intacte (la partie peut être reprise)
    session["game"] = state

    return jsonify({"ok": True, "redirect": "/", "message": "Partie sauvegardée."})


@app.post("/api/start_from_position")
def start_from_position():
    data = request.get_json(silent=True) or {}
    plateau = data.get("plateau")
    mode = int(data.get("mode", 1))
    jeton_actuel = int(data.get("jeton_actuel", 1))

    if not isinstance(plateau, list) or len(plateau) != NB_LIGNES:
        return jsonify({"ok": False, "error": "Plateau invalide"}), 400
    for row in plateau:
        if not isinstance(row, list) or len(row) != NB_COLONNES:
            return jsonify({"ok": False, "error": "Plateau invalide"}), 400
        if any(cell not in (0, 1, 2) for cell in row):
            return jsonify({"ok": False, "error": "Valeur de cellule invalide"}), 400

    if mode not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "Mode invalide"}), 400
    if jeton_actuel not in (1, 2):
        return jsonify({"ok": False, "error": "Jeton invalide"}), 400

    # Refuser les positions déjà gagnantes
    if verificationVictoire(plateau, NB_LIGNES, NB_COLONNES):
        return jsonify({"ok": False, "error": "La position contient déjà une victoire"}), 400

    id_partie_db = initialiser_partie_db(mode, NB_LIGNES, NB_COLONNES)
    state = {
        "mode": mode,
        "nb_lignes": NB_LIGNES,
        "nb_colonnes": NB_COLONNES,
        "plateau": plateau,
        "jeton_actuel": jeton_actuel,
        "jeu_en_cours": True,
        "historique": [],
        "historique_coups": "",
        "pions_gagnants": [],
        "scores_colonnes": [None] * NB_COLONNES,
        "dernier_score_ia": 0,
        "profondeur_ia": 9,
        "historique_futur": [],
        "id_partie_db": id_partie_db,
    }
    _compute_scores(state)
    session["game"] = state
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/clear_state")
def clear_state():
    session.pop("game", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
