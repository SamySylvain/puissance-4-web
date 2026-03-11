import random
import time
import json
import os
import mysql.connector

def creerPlateau(nbrLignes, nbrColonnes):
    plateauLocal = []
    for i in range(nbrLignes):
        ligne = [0] * nbrColonnes
        plateauLocal.append(ligne)
    return plateauLocal

def poserJeton(plateau, colonneChoisie, jetons):
    nbrLignes = len(plateau)
    if colonneChoisie < 0 or (nbrLignes > 0 and colonneChoisie >= len(plateau[0])):
        return False
    for ligne in range(nbrLignes - 1, -1, -1):
        if plateau[ligne][colonneChoisie] == 0:
            plateau[ligne][colonneChoisie] = jetons
            return ligne
    return False

def verificationVictoire(plateau, nbrLignes, nbrColonnes):
    directions = [(0, 1), (1, 0), (1, 1), (-1, 1)]
    for i in range(nbrLignes):
        for j in range(nbrColonnes):
            joueur = plateau[i][j]
            if joueur == 0:
                continue
            for di, dj in directions:
                pions = [(i, j)]
                ni, nj = i + di, j + dj
                while 0 <= ni < nbrLignes and 0 <= nj < nbrColonnes and plateau[ni][nj] == joueur:
                    pions.append((ni, nj))
                    ni += di
                    nj += dj
                ni, nj = i - di, j - dj
                while 0 <= ni < nbrLignes and 0 <= nj < nbrColonnes and plateau[ni][nj] == joueur:
                    pions.append((ni, nj))
                    ni -= di
                    nj -= dj
                if len(pions) >= 4:
                    return pions
    return None

def evaluer_segement(segment, jeton_ia):
    score = 0
    adversaire = 1 if jeton_ia == 2 else 2
    if segment.count(jeton_ia) == 4:
        score += 10000
    elif segment.count(jeton_ia) == 3 and segment.count(0) == 1:
        score += 100
    elif segment.count(jeton_ia) == 2 and segment.count(0) == 2:
        score += 10
    if segment.count(adversaire) == 3 and segment.count(0) == 1:
        score -= 99
    return score

def evaluer_plateau(plateau, jeton_ia, nbrLignes, nbrColonnes):
    score_total = 0
    for l in range(nbrLignes):
        ligne_entiere = plateau[l]
        for c in range(nbrColonnes - 3):
            segment = ligne_entiere[c:c+4]
            score_total += evaluer_segement(segment, jeton_ia)
    for c in range(nbrColonnes):
        colonne_entiere = [plateau[l][c] for l in range(nbrLignes)]
        for l in range(nbrLignes - 3):
            segment = colonne_entiere[l:l+4]
            score_total += evaluer_segement(segment, jeton_ia)
    for l in range(nbrLignes - 3):
        for c in range(nbrColonnes - 3):
            segment = [plateau[l+i][c+i] for i in range(4)]
            score_total += evaluer_segement(segment, jeton_ia)
    for l in range(3, nbrLignes):
        for c in range(nbrColonnes - 3):
            segment = [plateau[l-i][c+i] for i in range(4)]
            score_total += evaluer_segement(segment, jeton_ia)
    return score_total

def minimax(plateau, profondeur, maximisant, jeton_ia, nbrLignes, nbrColonnes):
    victorieux = verificationVictoire(plateau, nbrLignes, nbrColonnes)
    if profondeur == 0 or victorieux is not None:
        if victorieux:
            if plateau[victorieux[0][0]][victorieux[0][1]] == jeton_ia:
                return (1000000, None)
            else:
                return (-1000000, None)
        else:
            return (evaluer_plateau(plateau, jeton_ia, nbrLignes, nbrColonnes), None)
    colonnes_possibles = [c for c in range(nbrColonnes) if plateau[0][c] == 0]
    if not colonnes_possibles:
        return (0, None)
    if maximisant:
        valeur = -float('inf')
        meilleure_col = random.choice(colonnes_possibles)
        for col in colonnes_possibles:
            copie_plateau = [ligne[:] for ligne in plateau]
            poserJeton(copie_plateau, col, jeton_ia)
            nouveau_score = minimax(copie_plateau, profondeur - 1, False, jeton_ia, nbrLignes, nbrColonnes)[0]
            if nouveau_score > valeur:
                valeur = nouveau_score
                meilleure_col = col
        return valeur, meilleure_col
    else:
        valeur = float('inf')
        adversaire = 1 if jeton_ia == 2 else 2
        meilleure_col = random.choice(colonnes_possibles)
        for col in colonnes_possibles:
            copie_plateau = [ligne[:] for ligne in plateau]
            poserJeton(copie_plateau, col, adversaire)
            nouveau_score = minimax(copie_plateau, profondeur - 1, True, jeton_ia, nbrLignes, nbrColonnes)[0]
            if nouveau_score < valeur:
                valeur = nouveau_score
                meilleure_col = col
        return valeur, meilleure_col

def analyser_tous_les_coups(plateau, profondeur, jeton_joueur, nbrLignes, nbrColonnes):
    scores = {}
    colonnes_possibles = [c for c in range(nbrColonnes) if plateau[0][c] == 0]
    for col in colonnes_possibles:
        copie_plateau = [ligne[:] for ligne in plateau]
        poserJeton(copie_plateau, col, jeton_joueur)
        score = minimax(copie_plateau, profondeur - 1, False, jeton_joueur, nbrLignes, nbrColonnes)[0]
        scores[col] = score
    return scores


def connecter_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="puissance4"
    )

def delete_all_db():
    """Efface toutes les données de la base de données et réinitialise les compteurs."""
    try:
        db = connecter_db()
        cursor = db.cursor()
        # 1. On désactive les contraintes
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        # 2. On brise les liens récursifs (A/N) en mettant tout à NULL
        cursor.execute("UPDATE Partie SET id_antecedent = NULL, id_suivant = NULL")
        # 3. On vide les tables
        cursor.execute("DELETE FROM Situation")
        cursor.execute("DELETE FROM Partie")
        # 4. On réinitialise les compteurs d'ID à 1
        cursor.execute("ALTER TABLE Partie AUTO_INCREMENT = 1")
        cursor.execute("ALTER TABLE Situation AUTO_INCREMENT = 1")
        # 5. On réactive la sécurité
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        db.commit()
        cursor.close()
        db.close()
        return True, "Base de données complètement effacée et réinitialisée."
    except Exception as e:
        return False, f"Erreur lors de l'effacement : {e}"

def initialiser_partie_db(mode, nb_lignes=9, nb_colonnes=9):
    try:
        db = connecter_db()
        cursor = db.cursor()
        if mode == 1:
            confiance = 3
        elif mode == 2:
            confiance = 2
        elif mode == 3:
            confiance = 2
        else:
            confiance = 1
        sql_partie = "INSERT INTO Partie (coups, mode_jeu, statut, confiance, nb_colonnes) VALUES (%s, %s, %s, %s, %s)"
        try:
            cursor.execute(sql_partie, ("", mode, 'EN_COURS', confiance, nb_colonnes))
            id_partie = cursor.lastrowid
        except Exception as e:
            print(f"Warning initialiser_partie_db: insert with extra columns failed: {e}")
            cursor.execute("INSERT INTO Partie (coups, mode_jeu, statut) VALUES (%s, %s, %s)", ("", mode, 'EN_COURS'))
            id_partie = cursor.lastrowid
        plateau_vide = "0" * (nb_lignes * nb_colonnes)
        sql_situation = "INSERT INTO Situation (id_partie, plateau_hash) VALUES (%s, %s)"
        cursor.execute(sql_situation, (id_partie, plateau_vide))
        db.commit()
        cursor.close()
        db.close()
        return id_partie
    except Exception as e:
        print(f"Erreur init DB : {e}")
        return None

def recuperer_coups_db(id_partie):
    try:
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT coups FROM Partie WHERE id_partie = %s", (id_partie,))
        res = cursor.fetchone()
        db.close()
        return res['coups'] if res else ""
    except Exception as e:
        print(f"Erreur récup coups : {e}")
        return ""

def obtenir_forme_normale(plateau_actuel):
    mapping = {0: '0', 1: 'R', 2: 'J'}
    nbrLignes = len(plateau_actuel)
    nbrColonnes = len(plateau_actuel[0]) if nbrLignes > 0 else 0
    hash_normal = "".join(mapping[case] for ligne in plateau_actuel for case in ligne)
    lignes = [hash_normal[i:i+nbrColonnes] for i in range(0, nbrLignes * nbrColonnes, nbrColonnes)]
    hash_miroir = "".join(ligne[::-1] for ligne in lignes)
    return min(hash_normal, hash_miroir)

def obtenir_coups_miroir(coups_str, nb_colonnes=9):
    return "".join(str(nb_colonnes + 1 - int(c)) for c in coups_str)

def importer_partie_depuis_fichier(chemin_fichier):
    try:
        nom_fichier = os.path.basename(chemin_fichier)
        coups_extraits = nom_fichier.replace(".txt", "")
        if not coups_extraits.isdigit():
            return False, "Le nom du fichier doit contenir uniquement des chiffres."
        db = connecter_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id_partie FROM Partie WHERE coups = %s", (coups_extraits,))
        if cursor.fetchone():
            db.close()
            return False, f"La partie '{coups_extraits}' existe déjà dans la base."
        # On suppose 9x9 pour les importations depuis fichiers numérotés
        plateau_v = creerPlateau(9, 9)
        joueur = 1
        statut_final = 'EN_COURS'
        gagnants = None
        for char in coups_extraits:
            col = int(char) - 1
            if 0 <= col < 9:
                res_pose = poserJeton(plateau_v, col, joueur)
                if res_pose is not False:
                    win = verificationVictoire(plateau_v, 9, 9)
                    if win:
                        gagnants = win
                        statut_final = 'FIN_ROUGE' if joueur == 1 else 'FIN_JAUNE'
                        break
                    joueur = 3 - joueur
        sql = """
            INSERT INTO Partie (coups, mode_jeu, statut, type_donnee, pions_gagnants, confiance, nb_colonnes) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            cursor.execute(sql, (coups_extraits, 1, statut_final, 'IMPORT', str(gagnants), 3, 9))
            nouvel_id = cursor.lastrowid
        except Exception as e:
            print(f"Warning importer_partie_depuis_fichier: insert with extra columns failed: {e}")
            sql_old = "INSERT INTO Partie (coups, mode_jeu, statut, type_donnee, pions_gagnants) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql_old, (coups_extraits, 1, statut_final, 'IMPORT', str(gagnants)))
            nouvel_id = cursor.lastrowid
        plateau_hash = obtenir_forme_normale(plateau_v)
        cursor.execute("INSERT INTO Situation (id_partie, plateau_hash) VALUES (%s, %s)", (nouvel_id, plateau_hash))
        db.commit()
        db.close()
        actualiser_coup_db(nouvel_id, coups_extraits, plateau_v, statut_final, gagnants)
        return True, f"Partie {nouvel_id} importée (Statut: {statut_final})"
    except Exception as e:
        return False, f"Erreur lors de l'importation : {e}"

def actualiser_coup_db(id_partie, coups_str, plateau_actuel, statut='EN_COURS', gagnants=None):
    try:
        db = connecter_db()
        cursor = db.cursor(dictionary=True, buffered=True)
        plateau_hash = obtenir_forme_normale(plateau_actuel)
        cursor.execute("UPDATE Situation SET plateau_hash = %s WHERE id_partie = %s", (plateau_hash, id_partie))
        plateau_hash = obtenir_forme_normale(plateau_actuel)
        liste_ids_symetries = []
        query_sym = """
            SELECT P.id_partie
            FROM Situation S
            JOIN Partie P ON S.id_partie = P.id_partie
            WHERE S.plateau_hash = %s AND P.id_partie != %s
        """
        cursor.execute(query_sym, (plateau_hash, id_partie))
        resultats = cursor.fetchall()
        liste_ids_symetries = [row['id_partie'] for row in resultats]
        query_A = """
            SELECT id_partie FROM Partie 
            WHERE id_partie != %s AND coups != '' 
            AND (LENGTH(coups) < LENGTH(%s) OR (LENGTH(coups) = LENGTH(%s) AND coups < %s))
            ORDER BY LENGTH(coups) DESC, coups DESC LIMIT 1
        """
        cursor.execute(query_A, (id_partie, coups_str, coups_str, coups_str))
        res_A = cursor.fetchone()
        id_A = res_A['id_partie'] if res_A else None
        query_N = """
            SELECT id_partie FROM Partie 
            WHERE id_partie != %s AND coups != '' 
            AND (LENGTH(coups) > LENGTH(%s) OR (LENGTH(coups) = LENGTH(%s) AND coups > %s))
            ORDER BY LENGTH(coups) ASC, coups ASC LIMIT 1
        """
        cursor.execute(query_N, (id_partie, coups_str, coups_str, coups_str))
        res_N = cursor.fetchone()
        id_N = res_N['id_partie'] if res_N else None
        cursor.execute("UPDATE Partie SET id_suivant = NULL WHERE id_suivant = %s", (id_partie,))
        cursor.execute("UPDATE Partie SET id_antecedent = NULL WHERE id_antecedent = %s", (id_partie,))
        valeur_symetrie_json = json.dumps(liste_ids_symetries) if liste_ids_symetries else None
        sql_update_self = """
            UPDATE Partie 
            SET coups = %s, statut = %s, pions_gagnants = %s, 
                id_antecedent = %s, id_suivant = %s, id_symetrie = %s 
            WHERE id_partie = %s
        """
        cursor.execute(sql_update_self, (coups_str, statut, str(gagnants), id_A, id_N, valeur_symetrie_json, id_partie))
        if id_A:
            cursor.execute("UPDATE Partie SET id_suivant = %s WHERE id_partie = %s", (id_partie, id_A))
        if id_N:
            cursor.execute("UPDATE Partie SET id_antecedent = %s WHERE id_partie = %s", (id_partie, id_N))
        if liste_ids_symetries:
            for id_sym in liste_ids_symetries:
                cursor.execute("SELECT id_symetrie FROM Partie WHERE id_partie = %s", (id_sym,))
                res = cursor.fetchone()
                try:
                    liste_existante = json.loads(res['id_symetrie']) if res['id_symetrie'] else []
                except:
                    liste_existante = []
                if id_partie not in liste_existante:
                    liste_existante.append(id_partie)
                    cursor.execute("UPDATE Partie SET id_symetrie = %s WHERE id_partie = %s", (json.dumps(liste_existante), id_sym))
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f"Erreur lors de l'actualisation de la partie : {e}")


def sauvegarder_partie_bga(historique_coups, gagnant=None):
    """Insère une partie importée depuis BGA dans la base.

    - `historique_coups` : chaîne de chiffres '3425...'
    - `gagnant` : optionnel (1 ou 2). Si None, on déduit lors de la simulation.

    Crée la partie avec `confiance=3` et `nb_colonnes=7`.
    """
    try:
        nb_lignes = 6
        nb_colonnes = 7
        plateau_v = creerPlateau(nb_lignes, nb_colonnes)
        joueur = 1
        statut_final = 'EN_COURS'
        gagnants_positions = None

        # Simuler les coups pour déterminer le plateau final et le gagnant éventuel
        for ch in str(historique_coups):
            try:
                col = int(ch) - 1
            except:
                continue
            if 0 <= col < nb_colonnes:
                res_pose = poserJeton(plateau_v, col, joueur)
                if res_pose is not False:
                    win = verificationVictoire(plateau_v, nb_lignes, nb_colonnes)
                    if win:
                        gagnants_positions = win
                        statut_final = 'FIN_ROUGE' if joueur == 1 else 'FIN_JAUNE'
                        break
                    joueur = 3 - joueur

        db = connecter_db()
        cursor = db.cursor()
        sql = """
            INSERT INTO Partie (coups, mode_jeu, statut, type_donnee, pions_gagnants, confiance, nb_colonnes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            cursor.execute(sql, (historique_coups, 1, statut_final, 'BGA', str(gagnants_positions), 3, nb_colonnes))
            nouvel_id = cursor.lastrowid
        except Exception as e:
            # Fallback to simpler insert if schema differs
            cursor.execute("INSERT INTO Partie (coups, mode_jeu, statut) VALUES (%s, %s, %s)", (historique_coups, 1, statut_final))
            nouvel_id = cursor.lastrowid

        plateau_hash = obtenir_forme_normale(plateau_v)
        try:
            cursor.execute("INSERT INTO Situation (id_partie, plateau_hash) VALUES (%s, %s)", (nouvel_id, plateau_hash))
        except Exception:
            pass
        db.commit()
        db.close()

        # Mettre à jour la partie avec l'historique/plateau via la fonction existante
        actualiser_coup_db(nouvel_id, historique_coups, plateau_v, statut_final, gagnants_positions)
        return True, f"Partie BGA importée (id={nouvel_id})"
    except Exception as e:
        return False, f"Erreur sauvegarde BGA : {e}"
