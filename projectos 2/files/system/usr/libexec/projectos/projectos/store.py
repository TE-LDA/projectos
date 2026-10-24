"""Le magasin d'objets : index SQLite du service projetd.

Fidèle aux choix de la spécification :
- identité = UUID attribué une fois pour toutes (xattr + index) ;
- empreinte (BLAKE2b) et inode = indices de récupération seulement ;
- deux exemplaires d'un même contenu restent deux objets distincts ;
- l'index est reconstruisable : les sources font foi.
"""

import json
import os
import sqlite3
import time
import unicodedata
import uuid


def sans_accent(texte):
    """Recherche insensible aux accents : « électricité » trouve
    « electricite ». Normalisation des deux côtés, index et requête."""
    if not texte:
        return ""
    nkd = unicodedata.normalize("NFD", texte)
    return "".join(c for c in nkd if not unicodedata.combining(c)).lower()

DB_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projet (
    id           TEXT PRIMARY KEY,
    nom          TEXT NOT NULL,
    etat         TEXT NOT NULL DEFAULT 'actif',
    profil       TEXT NOT NULL DEFAULT 'atelier',
    teinte       TEXT,
    dossier      TEXT,              -- dossier racine déclaré (convention)
    signet       TEXT,              -- la note de reprise
    cree_le      TEXT,
    echeance     TEXT,
    derniere_visite TEXT
);

CREATE TABLE IF NOT EXISTS objet (
    id           TEXT PRIMARY KEY,  -- UUID : l'identité invariante
    fts_id       INTEGER,           -- rowid dans objet_fts (texte indexé)
    type         TEXT NOT NULL,     -- fichier | mail
    identite     TEXT NOT NULL UNIQUE,
    titre        TEXT,
    localisation TEXT,
    empreinte    TEXT,
    inode        INTEGER,
    taille       INTEGER,
    modifie_le   TEXT,
    metas        TEXT,              -- JSON (expéditeur, objet, compte…)
    sas_resolu   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attribution (
    projet_id    TEXT REFERENCES projet(id),
    objet_id     TEXT REFERENCES objet(id),
    origine      TEXT NOT NULL,     -- manuel | regle | connecteur
    regle_id     TEXT,
    attribue_le  TEXT,
    PRIMARY KEY (projet_id, objet_id)
);

CREATE TABLE IF NOT EXISTS regle (
    id        TEXT PRIMARY KEY,
    projet_id TEXT REFERENCES projet(id),
    type      TEXT NOT NULL,
    predicat  TEXT NOT NULL,        -- JSON
    phrase    TEXT NOT NULL,        -- la règle, en français
    active    INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_att_objet ON attribution(objet_id);

CREATE VIRTUAL TABLE IF NOT EXISTS objet_fts USING fts5(titre, contenu);
"""


def maintenant() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


class Store:
    """L'index. Toutes les opérations passent par ici."""

    def __init__(self, chemin_db: str):
        self.chemin = chemin_db
        neuf = not os.path.exists(chemin_db)
        self.db = sqlite3.connect(chemin_db)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DB_SCHEMA)
        if neuf:
            self.db.commit()

    # ------------------------------------------------------------- projets

    def projet_create(self, nom, profil="atelier", teinte=None,
                      dossier=None, echeance=None) -> str:
        pid = uuid.uuid4().hex[:8]
        while self.db.execute(
                "SELECT 1 FROM projet WHERE id=?", (pid,)).fetchone():
            pid = uuid.uuid4().hex[:8]
        self.db.execute(
            "INSERT INTO projet (id, nom, profil, teinte, dossier, echeance, cree_le)"
            " VALUES (?,?,?,?,?,?,?)",
            (pid, nom, profil, teinte, dossier, echeance, maintenant()))
        self.db.commit()
        return pid

    def projet(self, pid):
        return self.db.execute("SELECT * FROM projet WHERE id=?", (pid,)).fetchone()

    def projets(self, etat=None):
        if etat:
            return self.db.execute(
                "SELECT * FROM projet WHERE etat=? ORDER BY nom", (etat,)).fetchall()
        return self.db.execute("SELECT * FROM projet ORDER BY etat, nom").fetchall()

    def projet_par_nom(self, nom):
        rows = self.db.execute(
            "SELECT * FROM projet WHERE nom LIKE ?", (f"%{nom}%",)).fetchall()
        return rows[0] if rows else None

    # ------------------------------------------------------------- objets

    def objet_upsert(self, type_, identite, titre, localisation=None,
                     empreinte=None, inode=None, taille=None,
                     modifie_le=None, metas=None, contenu=None) -> tuple:
        """Crée ou met à jour un objet. Retourne (id, événement).

        Événement : 'nouveau', 'deplace', 'modifie', 'inchangé'.
        """
        row = self.db.execute(
            "SELECT * FROM objet WHERE identite=?", (identite,)).fetchone()
        metas_json = json.dumps(metas, ensure_ascii=False) if metas else None
        if row is None:
            oid = uuid.uuid4().hex
            cur = self.db.execute(
                "INSERT INTO objet (id, type, identite, titre, localisation,"
                " empreinte, inode, taille, modifie_le, metas)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (oid, type_, identite, titre, localisation, empreinte, inode,
                 taille, modifie_le, metas_json))
            try:
                # le rowid du FTS est le rowid interne de l'objet ; il est
                # reporté dans fts_id, seul lien fiable avec l'UUID.
                self.db.execute(
                    "INSERT INTO objet_fts (rowid, titre, contenu)"
                    " VALUES (?,?,?)",
                    (cur.lastrowid, sans_accent(titre), sans_accent(contenu)))
                self.db.execute("UPDATE objet SET fts_id=? WHERE id=?",
                                (cur.lastrowid, oid))
            except sqlite3.OperationalError:
                pass  # sans FTS5, l'index reste utilisable en LIKE
            self.db.commit()
            return oid, "nouveau"

        ev = "inchangé"
        maj = []
        if localisation and localisation != row["localisation"]:
            maj.append(("localisation", localisation)); ev = "deplace"
        if empreinte and empreinte != row["empreinte"]:
            maj.append(("empreinte", empreinte)); ev = "modifie"
        if titre and titre != row["titre"]:
            maj.append(("titre", titre))
        for champ, val in maj:
            self.db.execute(f"UPDATE objet SET {champ}=? WHERE id=?", (val, row["id"]))
        if maj:
            self.db.execute("UPDATE objet SET inode=?, taille=?, modifie_le=?,"
                            " metas=COALESCE(?, metas) WHERE id=?",
                            (inode, taille, modifie_le, metas_json, row["id"]))
            # Limite connue du prototype : l'index plein texte n'est pas
            # reconstruit à la modification d'un contenu (voir README).
            self.db.commit()
        return row["id"], ev

    def objet(self, oid):
        return self.db.execute("SELECT * FROM objet WHERE id=?", (oid,)).fetchone()

    def objets_sans_projet(self):
        return self.db.execute(
            "SELECT * FROM objet o WHERE sas_resolu=0 AND NOT EXISTS"
            " (SELECT 1 FROM attribution a WHERE a.objet_id=o.id)"
            " ORDER BY modifie_le DESC").fetchall()

    def rechercher(self, q, projet_id=None):
        """Recherche plein texte (FTS5), filtrable par projet, insensible
        aux accents."""
        q = sans_accent(q)
        sql = ("SELECT o.* FROM objet_fts f JOIN objet o ON o.fts_id=f.rowid"
               " WHERE objet_fts MATCH ?")
        args = [f'"{q}"*']
        if projet_id:
            sql += (" AND EXISTS (SELECT 1 FROM attribution a"
                    " WHERE a.objet_id=o.id AND a.projet_id=?)")
            args.append(projet_id)
        return self.db.execute(sql, args).fetchall()

    # -------------------------------------------------------- attributions

    def attribute(self, oid, pid, origine="manuel", regle_id=None) -> bool:
        existe = self.db.execute(
            "SELECT 1 FROM attribution WHERE projet_id=? AND objet_id=?",
            (pid, oid)).fetchone()
        if existe:
            return False
        self.db.execute(
            "INSERT INTO attribution (projet_id, objet_id, origine, regle_id,"
            " attribue_le) VALUES (?,?,?,?,?)",
            (pid, oid, origine, regle_id, maintenant()))
        self.db.execute("UPDATE objet SET sas_resolu=1 WHERE id=?", (oid,))
        self.db.commit()
        return True

    def desattribute(self, oid, pid):
        self.db.execute("DELETE FROM attribution WHERE projet_id=? AND objet_id=?",
                        (pid, oid))
        self.db.commit()

    def attributions(self, oid):
        return self.db.execute(
            "SELECT a.*, p.nom FROM attribution a JOIN projet p ON p.id=a.projet_id"
            " WHERE a.objet_id=?", (oid,)).fetchall()

    def objets_du_projet(self, pid, type_=None, apres=None):
        sql = ("SELECT o.*, a.origine FROM attribution a JOIN objet o"
               " ON o.id=a.objet_id WHERE a.projet_id=?")
        args = [pid]
        if type_:
            sql += " AND o.type=?"; args.append(type_)
        if apres:
            sql += " AND o.modifie_le > ?"; args.append(apres)
        sql += " ORDER BY o.modifie_le DESC"
        return self.db.execute(sql, args).fetchall()

    def ranger_hors_projet(self, oid):
        """Sort l'objet du sas sans l'attribuer : tout ne relève pas d'un projet."""
        self.db.execute("UPDATE objet SET sas_resolu=1 WHERE id=?", (oid,))
        self.db.commit()

    # -------------------------------------------------------------- règles

    def regle_add(self, pid, type_, predicat, phrase) -> str:
        # fusion : même projet, même type, même prédicat → pas de doublon
        pred_json = json.dumps(predicat, ensure_ascii=False, sort_keys=True)
        existante = self.db.execute(
            "SELECT id FROM regle WHERE projet_id=? AND type=? AND predicat=?",
            (pid, type_, pred_json)).fetchone()
        if existante:
            return existante["id"]
        rid = uuid.uuid4().hex[:8]
        self.db.execute(
            "INSERT INTO regle (id, projet_id, type, predicat, phrase)"
            " VALUES (?,?,?,?,?)", (rid, pid, type_, pred_json, phrase))
        self.db.commit()
        return rid

    def regles(self, pid=None, actives=True):
        sql = "SELECT * FROM regle"
        args, clauses = [], []
        if pid:
            clauses.append("projet_id=?"); args.append(pid)
        if actives:
            clauses.append("active=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY projet_id, id"
        return self.db.execute(sql, args).fetchall()

    def regle_desactive(self, rid):
        self.db.execute("UPDATE regle SET active=0 WHERE id=?", (rid,))
        self.db.commit()

    # ------------------------------------------------------------- divers

    def marquer_visite(self, pid):
        self.db.execute("UPDATE projet SET derniere_visite=? WHERE id=?",
                        (maintenant(), pid))
        self.db.commit()
