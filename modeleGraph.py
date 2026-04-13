import random
import time
import json
import os
try:
    import mysql.connector
except ImportError:
    mysql = None

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

# ===========================================================================
# Table positionnelle (cases centrales valent plus)
# ===========================================================================

_POS_TABLE_CACHE = {}

def _build_position_table(nbrLignes, nbrColonnes):
    cx = (nbrColonnes - 1) / 2
    cy = (nbrLignes - 1) / 2
    return [
        [max(0, 6 - (abs(c - cx) + abs(l - cy))) for c in range(nbrColonnes)]
        for l in range(nbrLignes)
    ]

def _get_pos_table(nbrLignes, nbrColonnes):
    key = (nbrLignes, nbrColonnes)
    if key not in _POS_TABLE_CACHE:
        _POS_TABLE_CACHE[key] = _build_position_table(nbrLignes, nbrColonnes)
    return _POS_TABLE_CACHE[key]

# ===========================================================================
# Évaluation inline — sans allocation de liste par fenêtre
# ===========================================================================

def _eval_w4(a, b, c, d, ia, adv):
    ni = (a == ia) + (b == ia) + (c == ia) + (d == ia)
    na = (a == adv) + (b == adv) + (c == adv) + (d == adv)
    if ni and na:  return 0
    if ni == 4:    return 100000
    if na == 4:    return -100000
    s = 0
    # Amélioration 2 : poids revus — attaque légèrement plus forte,
    # blocage adversaire nettement plus fort (éviter les défaites)
    if ni == 3:    s += 600    # était 500 — menacer 3-en-ligne vaut plus
    elif ni == 2:  s += 30     # était 20
    if na == 3:    s -= 550    # était -490 — bloquer 3-en-ligne adversaire vaut beaucoup plus
    elif na == 2:  s -= 22     # était -15
    return s

def _menaces_reelles(plateau, jeton, nL, nC):
    """
    Compte les menaces immédiates réelles : 3 jetons alignés et la 4ᵉ case vide
    est la prochaine case jouable de sa colonne (le jeton peut y tomber au prochain coup).
    Une double menace (≥2) est non-bloquable → victoire forcée.
    """
    adv = 3 - jeton
    # case la plus basse vide par colonne
    jouable = {}
    for c in range(nC):
        for r in range(nL - 1, -1, -1):
            if plateau[r][c] == 0:
                jouable[c] = r
                break

    count = 0

    def _check(cells):
        nonlocal count
        ni = na = 0
        vide = None
        for r, c in cells:
            v = plateau[r][c]
            if   v == jeton: ni += 1
            elif v == adv:   na += 1
            else:            vide = (r, c)
        if ni == 3 and na == 0 and vide and jouable.get(vide[1]) == vide[0]:
            count += 1

    for l in range(nL):
        for c in range(nC - 3):
            _check([(l, c+i) for i in range(4)])
    for c in range(nC):
        for l in range(nL - 3):
            _check([(l+i, c) for i in range(4)])
    for l in range(nL - 3):
        for c in range(nC - 3):
            _check([(l+i, c+i) for i in range(4)])
    for l in range(3, nL):
        for c in range(nC - 3):
            _check([(l-i, c+i) for i in range(4)])

    return count


def evaluer_plateau(plateau, jeton_ia, nbrLignes, nbrColonnes):
    adv = 3 - jeton_ia
    pos = _get_pos_table(nbrLignes, nbrColonnes)
    score = 0

    # Bonus positionnel
    for l in range(nbrLignes):
        row = plateau[l]; pt = pos[l]
        for c in range(nbrColonnes):
            v = row[c]
            if v == jeton_ia: score += pt[c]
            elif v:           score -= pt[c]

    # Fenêtres horizontales
    for l in range(nbrLignes):
        row = plateau[l]
        for c in range(nbrColonnes - 3):
            score += _eval_w4(row[c], row[c+1], row[c+2], row[c+3], jeton_ia, adv)

    # Fenêtres verticales
    for c in range(nbrColonnes):
        for l in range(nbrLignes - 3):
            score += _eval_w4(plateau[l][c], plateau[l+1][c], plateau[l+2][c], plateau[l+3][c], jeton_ia, adv)

    # Diagonales descendantes (\)
    for l in range(nbrLignes - 3):
        for c in range(nbrColonnes - 3):
            score += _eval_w4(plateau[l][c], plateau[l+1][c+1], plateau[l+2][c+2], plateau[l+3][c+3], jeton_ia, adv)

    # Diagonales montantes (/)
    for l in range(3, nbrLignes):
        for c in range(nbrColonnes - 3):
            score += _eval_w4(plateau[l][c], plateau[l-1][c+1], plateau[l-2][c+2], plateau[l-3][c+3], jeton_ia, adv)

    # Amélioration 2 : détection des menaces réelles jouables
    # (3 jetons alignés + 4e case vide et accessible immédiatement)
    # Une double menace (≥2) est ingagnable pour l'adversaire en un coup.
    nm_ia  = _menaces_reelles(plateau, jeton_ia, nbrLignes, nbrColonnes)
    nm_adv = _menaces_reelles(plateau, adv,      nbrLignes, nbrColonnes)
    if nm_ia >= 2:
        score += 48000   # Double menace IA → victoire quasi-certaine
    elif nm_ia == 1:
        score += 900     # Menace simple mais réelle
    if nm_adv >= 2:
        score -= 52000   # Double menace adversaire → urgence absolue de bloquer
    elif nm_adv == 1:
        score -= 850

    return score

# ===========================================================================
# Zobrist hashing
# ===========================================================================

_ZOBRIST = None
_ZOBRIST_DIMS = (0, 0)

def _init_zobrist(nL, nC):
    global _ZOBRIST, _ZOBRIST_DIMS
    if _ZOBRIST_DIMS == (nL, nC):
        return
    import random as _r
    rng = _r.Random(0x4F3A7C1B)
    # _ZOBRIST[joueur-1][ligne][col]
    _ZOBRIST = [
        [[rng.getrandbits(64) for _ in range(nC)] for _ in range(nL)]
        for _ in range(2)
    ]
    _ZOBRIST_DIMS = (nL, nC)

# ===========================================================================
# Détection de victoire incrémentale O(1) — autour du dernier jeton posé
# ===========================================================================

def _win_at(plateau, row, col, player, nL, nC):
    """Retourne True si player a ≥4 alignés en passant par (row, col)."""
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        cnt = 1
        r, c = row + dr, col + dc
        while 0 <= r < nL and 0 <= c < nC and plateau[r][c] == player:
            cnt += 1; r += dr; c += dc
        r, c = row - dr, col - dc
        while 0 <= r < nL and 0 <= c < nC and plateau[r][c] == player:
            cnt += 1; r -= dr; c -= dc
        if cnt >= 4:
            return True
    return False

# ===========================================================================
# Table de transposition + Killer moves
# ===========================================================================

_TT      = {}   # (hash, depth, maxi) -> (depth, score, col, flag)
_KILLERS = {}   # depth -> [col, ...]
_TT_MAX  = 1 << 22   # ~4M entrées max
_DEADLINE  = [None]  # timestamp limite
_TIMED_OUT = [False]
_NODE_IDX  = [0]

def _tt_store(key, depth, score, col, orig_alpha, beta):
    if len(_TT) >= _TT_MAX:
        return
    flag = 2 if score <= orig_alpha else (1 if score >= beta else 0)
    _TT[key] = (depth, score, col, flag)

def _add_killer(depth, col):
    k = _KILLERS.get(depth)
    if k is None:            _KILLERS[depth] = [col]
    elif col not in k:
        if len(k) < 2:       k.append(col)
        else:                k[1] = col

def _order_cols(cols, nC, depth, tt_col):
    ctr = (nC - 1) / 2
    killers = _KILLERS.get(depth, ())
    def key(c):
        if c == tt_col:   return -20.0
        if c in killers:  return -10.0 + abs(c - ctr)
        return abs(c - ctr)
    return sorted(cols, key=key)

# ===========================================================================
# Nœud récursif interne — plateau modifié in-place, puis restauré
# ===========================================================================

def _mm(plateau, depth, maxi, ia, adv, nL, nC, alpha, beta, heights, h, lm):
    # 0. Contrôle du temps (vérifié toutes les 4096 entrées)
    _NODE_IDX[0] += 1
    if _NODE_IDX[0] & 0x0FFF == 0 and _DEADLINE[0] is not None:
        if time.time() > _DEADLINE[0]:
            _TIMED_OUT[0] = True
    if _TIMED_OUT[0]:
        return 0, None

    # 1. Victoire du dernier coup (détection incrémentale O(1))
    if lm is not None:
        r, c, p = lm
        if _win_at(plateau, r, c, p, nL, nC):
            return (900000 + depth * 1000) if p == ia else (-900000 - depth * 1000), None

    # 2. Colonnes disponibles  (heights[c] = ligne la plus basse vide, -1 si pleine)
    cols = [c for c in range(nC) if heights[c] >= 0]
    if not cols:
        return 0, None

    # 3. Feuille heuristique
    if depth == 0:
        return evaluer_plateau(plateau, ia, nL, nC), None

    # 4. Table de transposition
    tt_key   = (h, depth, maxi)
    orig_alpha = alpha
    tt_col   = None
    entry    = _TT.get(tt_key)
    if entry is not None:
        td, ts, tc, tf = entry
        if td >= depth:
            if tf == 0: return ts, tc          # valeur exacte
            if tf == 1: alpha = max(alpha, ts) # borne inférieure
            else:       beta  = min(beta,  ts) # borne supérieure
            if alpha >= beta: return ts, tc
            tt_col = tc

    player  = ia if maxi else adv
    ordered = _order_cols(cols, nC, depth, tt_col)

    best_v = -10**9 if maxi else 10**9
    best_c = ordered[0]

    for col in ordered:
        row = heights[col]          # ligne la plus basse vide
        plateau[row][col] = player
        # Trouver la prochaine ligne vide au-dessus
        new_nr = -1
        for r in range(row - 1, -1, -1):
            if plateau[r][col] == 0:
                new_nr = r; break
        heights[col] = new_nr
        nh = h ^ _ZOBRIST[player - 1][row][col]

        v = _mm(plateau, depth - 1, not maxi, ia, adv,
                nL, nC, alpha, beta, heights, nh, (row, col, player))[0]

        plateau[row][col] = 0
        heights[col] = row          # restauration

        if maxi:
            if v > best_v: best_v = v; best_c = col
            if best_v > alpha: alpha = best_v
        else:
            if v < best_v: best_v = v; best_c = col
            if best_v < beta: beta = best_v

        if alpha >= beta:
            _add_killer(depth, col)
            break

        if _TIMED_OUT[0]:
            return best_v, best_c

    _tt_store(tt_key, depth, best_v, best_c, orig_alpha, beta)
    return best_v, best_c

# ===========================================================================
# Interface publique — compatible avec app.py
# ===========================================================================

def minimax(plateau, profondeur, maximisant, jeton_ia, nbrLignes, nbrColonnes,
            alpha=-float('inf'), beta=float('inf'), time_limit=2.0):
    """
    Minimax alpha-beta haute performance avec :
      - modification in-place du plateau (aucune copie)
      - détection de victoire incrémentale O(1)
      - table de transposition (Zobrist)
      - killer moves
      - approfondissement itératif (meilleure élagage alpha-beta)
      - contrôle de temps (time_limit secondes max)
    Retourne (score, meilleure_colonne).
    """
    global _TT, _KILLERS
    _init_zobrist(nbrLignes, nbrColonnes)
    _TT = {}
    _TIMED_OUT[0] = False
    _DEADLINE[0] = time.time() + time_limit if time_limit else None
    _NODE_IDX[0] = 0
    adv = 3 - jeton_ia

    # heights[c] = ligne la plus basse vide dans la colonne c (-1 si pleine)
    # Calcul exact : supporte les positions éditées (jetons flottants possibles)
    heights = []
    for c in range(nbrColonnes):
        nr = -1
        for r in range(nbrLignes - 1, -1, -1):
            if plateau[r][c] == 0:
                nr = r; break
        heights.append(nr)
    h = 0
    for r in range(nbrLignes):
        for c in range(nbrColonnes):
            v = plateau[r][c]
            if v:
                h ^= _ZOBRIST[v - 1][r][c]

    # Vérification terminale de l'état initial
    victorieux = verificationVictoire(plateau, nbrLignes, nbrColonnes)
    if victorieux is not None:
        gagnant = plateau[victorieux[0][0]][victorieux[0][1]]
        return (900000, None) if gagnant == jeton_ia else (-900000, None)

    cols = [c for c in range(nbrColonnes) if heights[c] >= 0]
    if not cols:
        return 0, None

    # ══════════════════════════════════════════════════════════════════
    # PRIORITÉ 1 — L'IA gagne immédiatement → jouer ce coup sans hésiter
    # ══════════════════════════════════════════════════════════════════
    for col in cols:
        row = heights[col]
        plateau[row][col] = jeton_ia
        won = _win_at(plateau, row, col, jeton_ia, nbrLignes, nbrColonnes)
        plateau[row][col] = 0
        if won:
            return 900000, col

    # ══════════════════════════════════════════════════════════════════
    # PRIORITÉ 2 — L'adversaire gagne immédiatement → bloquer absolument
    # ══════════════════════════════════════════════════════════════════
    menaces_imm = []
    for col in cols:
        row = heights[col]
        plateau[row][col] = adv
        if _win_at(plateau, row, col, adv, nbrLignes, nbrColonnes):
            menaces_imm.append(col)
        plateau[row][col] = 0

    if len(menaces_imm) == 1:
        # Une seule case de victoire adversaire → bloquer cette case, point final
        return -1, menaces_imm[0]

    if len(menaces_imm) >= 2:
        # Plusieurs menaces immédiates : impossible de tout bloquer en un coup.
        # Restreindre minimax aux seules cases bloquantes (jouer ailleurs = perdre
        # immédiatement sur le coup suivant, c'est inutile).
        best_v_b = -float('inf')
        best_col_b = menaces_imm[0]
        for col in menaces_imm:
            row = heights[col]
            plateau[row][col] = jeton_ia
            new_nr = -1
            for r in range(row - 1, -1, -1):
                if plateau[r][col] == 0:
                    new_nr = r; break
            heights[col] = new_nr
            nh = h ^ _ZOBRIST[jeton_ia - 1][row][col]

            v = _mm(plateau, max(1, profondeur - 1), False, jeton_ia, adv,
                    nbrLignes, nbrColonnes, -float('inf'), float('inf'),
                    heights, nh, (row, col, jeton_ia))[0]

            plateau[row][col] = 0
            heights[col] = row   # restaurer

            if v > best_v_b:
                best_v_b = v
                best_col_b = col
        return best_v_b, best_col_b

    # ══════════════════════════════════════════════════════════════════
    # PRIORITÉ 3 — Minimax normal (approfondissement itératif)
    # ══════════════════════════════════════════════════════════════════

    # Approfondissement itératif : depth 1 → profondeur
    # La TT des niveaux précédents améliore l'ordre des coups au niveau suivant
    best_score, best_col = 0, cols[len(cols) // 2]
    for d in range(1, profondeur + 1):
        _KILLERS = {}
        _NODE_IDX[0] = 0
        s, c = _mm(plateau, d, maximisant, jeton_ia, adv,
                   nbrLignes, nbrColonnes, -float('inf'), float('inf'), heights, h, None)
        if _TIMED_OUT[0]:
            break  # Résultat incomplet à cette profondeur → garder le meilleur précédent
        if c is not None:
            best_score, best_col = s, c
        # Victoire/défaite forcée trouvée → inutile d'aller plus loin
        if abs(s) >= 900000:
            break

    return best_score, best_col


def analyser_tous_les_coups(plateau, profondeur, jeton_joueur, nbrLignes, nbrColonnes):
    """Évalue le score de chaque colonne jouable (pour les hints visuels)."""
    global _TT, _KILLERS
    _init_zobrist(nbrLignes, nbrColonnes)
    _TT = {}
    _TIMED_OUT[0] = False
    _DEADLINE[0] = None
    _NODE_IDX[0] = 0
    _KILLERS = {}
    adv = 3 - jeton_joueur
    scores = {}

    heights = []
    for c in range(nbrColonnes):
        nr = -1
        for r in range(nbrLignes - 1, -1, -1):
            if plateau[r][c] == 0:
                nr = r; break
        heights.append(nr)
    h = 0
    for r in range(nbrLignes):
        for c in range(nbrColonnes):
            v = plateau[r][c]
            if v:
                h ^= _ZOBRIST[v - 1][r][c]

    cols = [c for c in range(nbrColonnes) if heights[c] >= 0]

    # --- Détection prioritaire des victoires/menaces immédiates ---

    # 1. Le joueur courant gagne immédiatement ?
    victoires_imm = set()
    for col in cols:
        row_t = heights[col]
        plateau[row_t][col] = jeton_joueur
        if _win_at(plateau, row_t, col, jeton_joueur, nbrLignes, nbrColonnes):
            victoires_imm.add(col)
        plateau[row_t][col] = 0

    # 2. L'adversaire gagne immédiatement (à bloquer en priorité) ?
    menaces_adv = set()
    for col in cols:
        row_t = heights[col]
        plateau[row_t][col] = adv
        if _win_at(plateau, row_t, col, adv, nbrLignes, nbrColonnes):
            menaces_adv.add(col)
        plateau[row_t][col] = 0

    for col in cols:
        row = heights[col]
        plateau[row][col] = jeton_joueur
        new_nr = -1
        for r in range(row - 1, -1, -1):
            if plateau[r][col] == 0:
                new_nr = r; break
        heights[col] = new_nr
        nh = h ^ _ZOBRIST[jeton_joueur - 1][row][col]

        if col in victoires_imm:
            scores[col] = 900000
        elif menaces_adv and col not in menaces_adv:
            # Ne pas bloquer = perdre immédiatement sur le coup suivant.
            # Cette pénalité doit être PLUS BASSE que tout score minimax possible
            # (les scores minimax sont bornés à ±(900000 + profondeur*1000) ≈ ±910000).
            scores[col] = -10_000_000
        elif profondeur <= 1:
            scores[col] = evaluer_plateau(plateau, jeton_joueur, nbrLignes, nbrColonnes)
        else:
            scores[col] = _mm(plateau, profondeur - 1, False, jeton_joueur, adv,
                               nbrLignes, nbrColonnes, -float('inf'), float('inf'),
                               heights, nh, (row, col, jeton_joueur))[0]

        plateau[row][col] = 0
        heights[col] = row

    return scores


# ---------------------------------------------------------------------------
# Base de données (inchangé)
# ---------------------------------------------------------------------------

def connecter_db():
    if mysql is None:
        raise RuntimeError("MySQL connector non disponible.")
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "puissance4")
    )

def delete_all_db():
    """Efface toutes les données de la base de données et réinitialise les compteurs."""
    try:
        db = connecter_db()
        cursor = db.cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("UPDATE Partie SET id_antecedent = NULL, id_suivant = NULL")
        cursor.execute("DELETE FROM Situation")
        cursor.execute("DELETE FROM Partie")
        cursor.execute("ALTER TABLE Partie AUTO_INCREMENT = 1")
        cursor.execute("ALTER TABLE Situation AUTO_INCREMENT = 1")
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
    try:
        nb_lignes = 6
        nb_colonnes = 7
        plateau_v = creerPlateau(nb_lignes, nb_colonnes)
        joueur = 1
        statut_final = 'EN_COURS'
        gagnants_positions = None

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
            cursor.execute("INSERT INTO Partie (coups, mode_jeu, statut) VALUES (%s, %s, %s)", (historique_coups, 1, statut_final))
            nouvel_id = cursor.lastrowid

        plateau_hash = obtenir_forme_normale(plateau_v)
        try:
            cursor.execute("INSERT INTO Situation (id_partie, plateau_hash) VALUES (%s, %s)", (nouvel_id, plateau_hash))
        except Exception:
            pass
        db.commit()
        db.close()

        actualiser_coup_db(nouvel_id, historique_coups, plateau_v, statut_final, gagnants_positions)
        return True, f"Partie BGA importée (id={nouvel_id})"
    except Exception as e:
        return False, f"Erreur sauvegarde BGA : {e}"
