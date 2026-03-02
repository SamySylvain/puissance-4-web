import os
import random
from flask import Flask, jsonify, render_template, request, session

from modeleGraph import (
    analyser_tous_les_coups,
    creerPlateau,
    minimax,
    poserJeton,
    verificationVictoire,
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
        profondeur_scores = max(1, min(profondeur_scores, 2))
        scores = analyser_tous_les_coups(
            state["plateau"], profondeur_scores, state["jeton_actuel"], NB_LIGNES, NB_COLONNES
        )
        for col, score in scores.items():
            state["scores_colonnes"][col] = score


def _new_state(mode):
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
        "profondeur_ia": 3,
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
    else:
        state["jeton_actuel"] = 2 if state["jeton_actuel"] == 1 else 1

    _compute_scores(state)
    return True, None


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
    profondeur = max(1, min(profondeur, 3))

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
    state["profondeur_ia"] = max(1, min(profondeur, 3))
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

    l, c = state["historique"].pop()
    state["plateau"][l][c] = 0
    state["jeton_actuel"] = 1 if state["jeton_actuel"] == 2 else 2
    if state["historique_coups"]:
        state["historique_coups"] = state["historique_coups"][:-1]

    if state["mode"] == 2 and len(state["historique"]) > 0:
        l, c = state["historique"].pop()
        state["plateau"][l][c] = 0
        state["jeton_actuel"] = 1 if state["jeton_actuel"] == 2 else 2
        if state["historique_coups"]:
            state["historique_coups"] = state["historique_coups"][:-1]

    state["jeu_en_cours"] = True
    state["pions_gagnants"] = []
    _compute_scores(state)

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


@app.post("/api/clear_state")
def clear_state():
    session.pop("game", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
