import io
import os
import random
import uuid
from flask import Flask, jsonify, render_template, request, Response

from modeleGraph import (
    analyser_tous_les_coups,
    creerPlateau,
    minimax,
    poserJeton,
    verificationVictoire,
    initialiser_partie_db,
    actualiser_coup_db,
    connecter_db,
    delete_all_db,
    importer_partie_depuis_fichier,
)


app = Flask(__name__)
app.secret_key = "puissance4-web-secret"

NB_LIGNES = 9
NB_COLONNES = 9

# Dictionnaire des parties en cours : game_id -> state
games = {}


def _gid():
    """Lit le game_id depuis le corps JSON ou les paramètres de requête."""
    data = request.get_json(silent=True) or {}
    return data.get("gid") or request.args.get("gid")


def _get_state(gid):
    return games.get(gid)


def _save_state(gid, state):
    games[gid] = state


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


def _new_state(mode, human_jeton=1, jeton_initial=1):
    id_partie_db = initialiser_partie_db(mode, NB_LIGNES, NB_COLONNES)
    state = {
        "mode": mode,
        "human_jeton": human_jeton,
        "nb_lignes": NB_LIGNES,
        "nb_colonnes": NB_COLONNES,
        "plateau": creerPlateau(NB_LIGNES, NB_COLONNES),
        "jeton_actuel": jeton_initial,
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
        statut_final = "FIN_ROUGE" if state["jeton_actuel"] == 1 else "FIN_JAUNE"
        _sync_db(state, statut=statut_final, gagnants=resultat)
    else:
        state["jeton_actuel"] = 2 if state["jeton_actuel"] == 1 else 1
        _sync_db(state)

    _compute_scores(state)
    return True, None


def _sync_db(state, statut="EN_COURS", gagnants=None):
    id_partie = state.get("id_partie_db")
    if id_partie is None:
        return
    try:
        actualiser_coup_db(id_partie, state["historique_coups"], state["plateau"], statut, gagnants)
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
    score, col = minimax(state["plateau"], profondeur, True, state["jeton_actuel"], NB_LIGNES, NB_COLONNES)
    if col is not None:
        _play_move(state, col)
    state["dernier_score_ia"] = score


# ── Pages ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/saves")
def saves_page():
    return render_template("saves.html")


@app.route("/bdd")
def bdd_page():
    return render_template("bdd.html")


@app.route("/visualiser")
def visualiser_page():
    return render_template("visualiser.html")


# ── API jeu ──────────────────────────────────────────────

@app.post("/api/new_game")
def new_game():
    data = request.get_json(silent=True) or {}
    mode = int(data.get("mode", 1))
    human_jeton = int(data.get("human_jeton", 1))
    jeton_initial = int(data.get("jeton_initial", 1))

    if mode not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "Mode invalide"}), 400
    if human_jeton not in (1, 2):
        return jsonify({"ok": False, "error": "human_jeton invalide"}), 400
    if jeton_initial not in (1, 2):
        return jsonify({"ok": False, "error": "jeton_initial invalide"}), 400

    # Réutiliser le gid existant ou en créer un nouveau
    gid = data.get("gid") or str(uuid.uuid4())
    state = _new_state(mode, human_jeton, jeton_initial)
    _save_state(gid, state)
    return jsonify({"ok": True, "gid": gid, "state": _state_for_response(state)})


@app.get("/api/state")
def get_state():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie en cours"}), 404
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/set_depth")
def set_depth():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    data = request.get_json(silent=True) or {}
    profondeur = int(data.get("depth", 3))
    state["profondeur_ia"] = max(1, min(profondeur, 9))
    _compute_scores(state)
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/set_mode")
def set_mode():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    data = request.get_json(silent=True) or {}
    mode = int(data.get("mode", state["mode"]))
    if mode not in (1, 2, 3, 4):
        return jsonify({"ok": False, "error": "Mode invalide"}), 400

    state["mode"] = mode
    _compute_scores(state)
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/play")
def play():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    data = request.get_json(silent=True) or {}
    colonne = int(data.get("col", -1))

    ai_jeton = 3 - state.get("human_jeton", 1)
    if state["mode"] in (2, 4) and state["jeton_actuel"] == ai_jeton:
        return jsonify({"ok": False, "error": "Tour de l'IA"}), 400
    if state["mode"] == 3:
        return jsonify({"ok": False, "error": "Mode IA vs IA"}), 400

    ok, err = _play_move(state, colonne)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400

    state["historique_futur"] = []
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/ai_move")
def ai_move():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404
    if state["mode"] not in (2, 4):
        return jsonify({"ok": False, "error": "Disponible uniquement en mode Joueur vs IA"}), 400
    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "Partie terminée"}), 400

    ai_jeton = 3 - state.get("human_jeton", 1)
    if state["jeton_actuel"] != ai_jeton:
        return jsonify({"ok": False, "error": "Ce n'est pas le tour de l'IA"}), 400

    _ai_play_once(state)
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/ai_step")
def ai_step():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404
    if state["mode"] != 3:
        return jsonify({"ok": False, "error": "Disponible uniquement en mode IA vs IA"}), 400

    if state["jeu_en_cours"]:
        _ai_play_once(state)

    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/undo")
def undo():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404
    if len(state["historique"]) == 0:
        return jsonify({"ok": False, "error": "Aucun coup à annuler"}), 400

    futur = state.setdefault("historique_futur", [])
    l, c = state["historique"].pop()
    futur.append([l, c])
    state["jeton_actuel"] = state["plateau"][l][c]
    state["plateau"][l][c] = 0
    if state["historique_coups"]:
        state["historique_coups"] = state["historique_coups"][:-1]

    if state["mode"] in (2, 4) and len(state["historique"]) > 0:
        l, c = state["historique"].pop()
        futur.append([l, c])
        state["jeton_actuel"] = state["plateau"][l][c]
        state["plateau"][l][c] = 0
        if state["historique_coups"]:
            state["historique_coups"] = state["historique_coups"][:-1]

    state["jeu_en_cours"] = True
    state["pions_gagnants"] = []
    _sync_db(state, statut="EN_COURS", gagnants=None)
    _compute_scores(state)
    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/redo")
def redo():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404

    futur = state.setdefault("historique_futur", [])
    if not futur:
        return jsonify({"ok": False, "error": "Rien à rejouer"}), 400

    nb = 2 if state["mode"] in (2, 4) and len(futur) >= 2 else 1
    for _ in range(nb):
        if not futur:
            break
        l, c = futur.pop()
        _play_move(state, c)

    return jsonify({"ok": True, "state": _state_for_response(state)})


@app.post("/api/abandon")
def abandon():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404
    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "La partie est déjà terminée"}), 400

    state["jeu_en_cours"] = False
    state["pions_gagnants"] = []
    state["scores_colonnes"] = [None] * NB_COLONNES
    statut_abandon = "ABANDON_ROUGE" if state["jeton_actuel"] == 1 else "ABANDON_JAUNE"
    _sync_db(state, statut=statut_abandon, gagnants=None)
    return jsonify({"ok": True, "state": _state_for_response(state), "message": "Partie abandonnée."})


@app.post("/api/load")
def load_saved():
    data = request.get_json(silent=True) or {}
    saved_state = data.get("state")
    if not isinstance(saved_state, dict):
        return jsonify({"ok": False, "error": "Données invalides"}), 400

    required_keys = {
        "mode", "nb_lignes", "nb_colonnes", "plateau", "jeton_actuel",
        "jeu_en_cours", "historique", "historique_coups", "pions_gagnants",
        "scores_colonnes", "dernier_score_ia", "profondeur_ia",
    }
    if not required_keys.issubset(saved_state.keys()):
        return jsonify({"ok": False, "error": "Sauvegarde incomplète"}), 400

    if "human_jeton" not in saved_state:
        saved_state["human_jeton"] = 1

    gid = data.get("gid") or str(uuid.uuid4())
    _save_state(gid, saved_state)
    return jsonify({"ok": True, "gid": gid, "state": _state_for_response(saved_state)})


@app.post("/api/save")
def save_game():
    gid = _gid()
    state = _get_state(gid)
    if not state:
        return jsonify({"ok": False, "error": "Aucune partie"}), 404
    if not state["jeu_en_cours"]:
        return jsonify({"ok": False, "error": "La partie est déjà terminée"}), 400

    _sync_db(state, statut="SAVE", gagnants=None)
    return jsonify({"ok": True, "redirect": "/", "message": "Partie sauvegardée."})


@app.post("/api/start_from_position")
def start_from_position():
    data = request.get_json(silent=True) or {}
    plateau = data.get("plateau")
    mode = int(data.get("mode", 1))
    jeton_actuel = int(data.get("jeton_actuel", 1))
    human_jeton = int(data.get("human_jeton", 1))

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
    if verificationVictoire(plateau, NB_LIGNES, NB_COLONNES):
        return jsonify({"ok": False, "error": "La position contient déjà une victoire"}), 400

    id_partie_db = initialiser_partie_db(mode, NB_LIGNES, NB_COLONNES)
    state = {
        "mode": mode,
        "human_jeton": human_jeton,
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
    gid = data.get("gid") or str(uuid.uuid4())
    _save_state(gid, state)
    return jsonify({"ok": True, "gid": gid, "state": _state_for_response(state)})


@app.post("/api/clear_state")
def clear_state():
    gid = _gid()
    if gid and gid in games:
        del games[gid]
    return jsonify({"ok": True})


# ── API BDD ──────────────────────────────────────────────

@app.get("/api/bdd_partie/<int:id_partie>")
def bdd_partie(id_partie):
    try:
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT coups, mode_jeu, statut, pions_gagnants FROM Partie WHERE id_partie = %s",
            (id_partie,)
        )
        row = cursor.fetchone()
        db.close()
        if not row:
            return jsonify({"ok": False, "error": "Partie introuvable"}), 404
        return jsonify({
            "ok": True,
            "coups": row["coups"] or "",
            "mode": row["mode_jeu"],
            "statut": row["statut"] or "",
            "gagnants": row["pions_gagnants"] or "",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/bdd_parties")
def bdd_parties():
    try:
        limit  = max(1, int(request.args.get("limit",  100)))
        offset = max(0, int(request.args.get("offset", 0)))
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM Partie")
        total = cursor.fetchone()["total"]
        cursor.execute(
            """SELECT id_partie, coups, mode_jeu, statut, pions_gagnants,
                      id_antecedent, id_suivant, id_symetrie, date_creation
               FROM Partie ORDER BY id_partie DESC
               LIMIT %s OFFSET %s""",
            (limit, offset)
        )
        rows = cursor.fetchall()
        db.close()
        parties = []
        for r in rows:
            parties.append({
                "id": r["id_partie"],
                "coups": r["coups"] or "",
                "mode": r["mode_jeu"],
                "statut": r["statut"] or "",
                "gagnants": r["pions_gagnants"] or "-",
                "antecedent": r["id_antecedent"] if r["id_antecedent"] else "-",
                "suivant": r["id_suivant"] if r["id_suivant"] else "-",
                "symetrie": r["id_symetrie"] if r["id_symetrie"] else "[]",
                "date": str(r["date_creation"]) if r["date_creation"] else "-",
            })
        return jsonify({"ok": True, "parties": parties, "total": total, "offset": offset, "limit": limit})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bdd_import")
def bdd_import():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Aucun fichier fourni"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".txt"):
        return jsonify({"ok": False, "error": "Le fichier doit être un .txt"}), 400
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt",
                                     prefix=os.path.splitext(f.filename)[0] + "_") as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name
    dir_ = os.path.dirname(tmp_path)
    final_path = os.path.join(dir_, f.filename)
    os.replace(tmp_path, final_path)
    try:
        succes, message = importer_partie_depuis_fichier(final_path)
    finally:
        try:
            os.remove(final_path)
        except Exception:
            pass
    if succes:
        return jsonify({"ok": True, "message": message})
    return jsonify({"ok": False, "error": message}), 400


@app.get("/api/bdd_export")
def bdd_export():
    try:
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT coups, mode_jeu, statut, pions_gagnants FROM Partie ORDER BY id_partie ASC")
        rows = cursor.fetchall()
        db.close()
        lines = ["coups;mode_jeu;statut;pions_gagnants"]
        for r in rows:
            coups    = r["coups"] or ""
            mode     = str(r["mode_jeu"] or "")
            statut   = r["statut"] or ""
            gagnants = (r["pions_gagnants"] or "").replace(";", ",")
            lines.append(f"{coups};{mode};{statut};{gagnants}")
        return Response(
            "\n".join(lines),
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=bdd_puissance4.ssv"}
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bdd_import_ssv")
def bdd_import_ssv():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Aucun fichier fourni"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".ssv"):
        return jsonify({"ok": False, "error": "Le fichier doit être un .ssv"}), 400
    try:
        content = f.read().decode("utf-8")
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not lines:
            return jsonify({"ok": False, "error": "Fichier vide"}), 400
        start = 1 if lines[0].startswith("coups;") else 0
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        inseres = ignores = 0
        for line in lines[start:]:
            parts = line.split(";", 3)
            if len(parts) < 2:
                continue
            coups    = parts[0].strip()
            mode     = int(parts[1].strip()) if parts[1].strip().isdigit() else 1
            statut   = parts[2].strip() if len(parts) > 2 else "EN_COURS"
            gagnants = parts[3].strip() if len(parts) > 3 else ""
            cursor.execute("SELECT id_partie FROM Partie WHERE coups = %s", (coups,))
            if cursor.fetchone():
                ignores += 1
                continue
            try:
                cursor.execute(
                    "INSERT INTO Partie (coups, mode_jeu, statut, pions_gagnants) VALUES (%s, %s, %s, %s)",
                    (coups, mode, statut, gagnants or None)
                )
                inseres += 1
            except Exception:
                ignores += 1
        db.commit()
        db.close()
        return jsonify({"ok": True, "message": f"{inseres} partie(s) importée(s), {ignores} ignorée(s) (doublons)."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/bdd_delete/<int:id_partie>")
def bdd_delete_one(id_partie):
    try:
        db = connecter_db()
        cursor = db.cursor()
        cursor.execute("UPDATE Partie SET id_antecedent = NULL WHERE id_antecedent = %s", (id_partie,))
        cursor.execute("UPDATE Partie SET id_suivant = NULL WHERE id_suivant = %s", (id_partie,))
        cursor.execute("UPDATE Partie SET id_symetrie = NULL WHERE id_symetrie = %s", (id_partie,))
        cursor.execute("DELETE FROM Situation WHERE id_partie = %s", (id_partie,))
        cursor.execute("DELETE FROM Partie WHERE id_partie = %s", (id_partie,))
        db.commit()
        db.close()
        return jsonify({"ok": True, "message": f"Partie {id_partie} supprimée."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bdd_delete_all")
def bdd_delete_all():
    succes, message = delete_all_db()
    if succes:
        return jsonify({"ok": True, "message": message})
    return jsonify({"ok": False, "error": message}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
