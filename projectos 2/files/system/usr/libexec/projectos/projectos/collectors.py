"""Les collecteurs : fichiers et courrier.

Ils suivent les sources sans les modifier. Ce prototype balaye à la
demande (la version réelle utilisera fanotify/inotify et mbsync) ;
le contrat — ne rien déplacer, ne rien copier — est le même.
"""

import os
import time
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

from .identity import (empreinte, identite_fichier, identite_mail,
                       inscrire_uuid_xattr)

EXCLUS = {"index.db", ".projectos"}


def _domaine(adresse):
    _, _, domaine = parseaddr(adresse)[1].partition("@")
    return domaine.lower() or adresse.lower()


def _lire_mail(path, compte):
    """Analyse un fichier mail (maildir) : en-têtes utiles seulement."""
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    metas = {
        "de": parseaddr(msg.get("From", ""))[1],
        "domaine": _domaine(msg.get("From", "")),
        "objet": str(msg.get("Subject", "")).replace("\n", " "),
        "date": str(msg.get("Date", "")),
        "compte": compte,
    }
    return metas, msg.get("Message-ID")


TEXTUEL = {".md", ".txt", ".csv", ".eml"}


def _texte_fichier(path, taille):
    """Le texte des fichiers texte, pour la recherche plein texte.
    Les formats binaires (PDF, .docx) exigent des extracteurs —
    hors périmètre du prototype, voir le README."""
    import os
    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXTUEL or taille > (2 << 20):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(1 << 20)
    except OSError:
        return None


def scan_fichiers(store, racine):
    """Indexe les fichiers de `racine`. Retourne des statistiques."""
    stats = {"nouveaux": 0, "deplaces": 0, "retrouves": 0, "total": 0}
    racine = os.path.abspath(racine)
    for dossier, sous_dossiers, fichiers in os.walk(racine):
        sous_dossiers[:] = [d for d in sous_dossiers
                            if d not in EXCLUS and not d.startswith(".")]
        for nom in fichiers:
            if nom.startswith(".") or nom in EXCLUS:
                continue
            path = os.path.join(dossier, nom)
            try:
                st = os.stat(path)
                if not os.path.isfile(path) or st.st_size > 64 << 20:
                    continue
            except OSError:
                continue
            stats["total"] += 1
            oid, commentaire = identite_fichier(store, path)
            if oid:
                # survie : mise à jour de la localisation et de l'empreinte
                emp, taille = empreinte(path)
                _, ev = store.objet_upsert(
                    "fichier", oid, nom, path, emp, st.st_ino, taille,
                    time.strftime("%Y-%m-%dT%H:%M:%S",
                                  time.localtime(st.st_mtime)))
                inscrire_uuid_xattr(path, oid)
                if ev == "deplace":
                    stats["deplaces"] += 1
                    stats["retrouves"] += 1
            else:
                emp, taille = empreinte(path)
                oid, ev = store.objet_upsert(
                    "fichier", f"fichier:{emp}:{taille}", nom, path, emp,
                    st.st_ino, taille,
                    time.strftime("%Y-%m-%dT%H:%M:%S",
                                  time.localtime(st.st_mtime)),
                    contenu=_texte_fichier(path, st.st_size))
                inscrire_uuid_xattr(path, oid)
                # l'identité devient l'UUID ; on garde l'empreinte en indice
                store.db.execute("UPDATE objet SET identite=? WHERE id=?",
                                 (oid, oid))
                store.db.commit()
                stats["nouveaux"] += 1
            _appliquer_regles_fichier(store, oid, path)
    return stats


def _appliquer_regles_fichier(store, oid, path):
    """Règles fichiers : la convention « un dossier par projet »."""
    import json
    for regle in store.db.execute(
            "SELECT * FROM regle WHERE type='dossier' AND active=1").fetchall():
        cible = json.loads(regle["predicat"]).get("dossier", "")
        if cible and path.startswith(cible + os.sep):
            store.attribute(oid, regle["projet_id"], "connecteur", regle["id"])
            return


def scan_courrier(store, racine_courrier):
    """Indexe les comptes maildir de `racine_courrier` (lecture seule)."""
    stats = {"nouveaux": 0, "total": 0}
    racine_courrier = os.path.abspath(racine_courrier)
    if not os.path.isdir(racine_courrier):
        return stats
    for compte in sorted(os.listdir(racine_courrier)):
        base = os.path.join(racine_courrier, compte)
        if not os.path.isdir(base) or compte.startswith("."):
            continue
        for sous in ("new", "cur"):
            d = os.path.join(base, sous)
            if not os.path.isdir(d):
                continue
            for nom in sorted(os.listdir(d)):
                path = os.path.join(d, nom)
                try:
                    if not os.path.isfile(path):
                        continue
                except OSError:
                    continue
                stats["total"] += 1
                try:
                    metas, mid = _lire_mail(path, compte)
                except Exception:
                    continue
                identite = identite_mail(compte, mid, metas)
                corps = ""
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        corps = f.read(1 << 20)
                except OSError:
                    pass
                oid, ev = store.objet_upsert(
                    "mail", identite, metas["objet"], path, None, None,
                    None, metas.get("date"), metas, contenu=corps)
                if ev == "nouveau":
                    stats["nouveaux"] += 1
                _appliquer_regles_mail(store, oid, metas)
    return stats


def _appliquer_regles_mail(store, oid, metas):
    """Évalue les règles mail actives. Chaque attribution cite sa règle."""
    import json
    for regle in store.db.execute(
            "SELECT * FROM regle WHERE type='mail' AND active=1").fetchall():
        pred = json.loads(regle["predicat"])
        expediteurs = pred.get("expediteur_contient", [])
        objets = pred.get("objet_contient", [])
        if any(e and e in metas["domaine"] for e in expediteurs):
            store.attribute(oid, regle["projet_id"], "regle", regle["id"])
            return
        if any(o and o.lower() in metas["objet"].lower() for o in objets):
            store.attribute(oid, regle["projet_id"], "regle", regle["id"])
            return
