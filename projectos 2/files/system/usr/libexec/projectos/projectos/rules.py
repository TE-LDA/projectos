"""Les règles, écrites en français.

Aucune inférence : une règle est un prédicat lisible, affiché comme
une phrase. Ranger un mail du sas crée ou complète la règle du
projet — la suggestion validée apprend *explicitement*.
"""

import json
import re

TOKENS_SANS = {"projet", "avec", "pour", "dossier", "site", "note"}


def phrase_regle_expéditeur(domaine, nom_projet):
    return f"Les mails venant de {domaine} vont dans {nom_projet}."


def phrase_regle_objet(mot, nom_projet):
    return f"Les mails dont l'objet contient « {mot} » vont dans {nom_projet}."


def phrase_regle_dossier(dossier, nom_projet):
    return (f"Les fichiers enregistrés dans {dossier}"
            f" vont dans {nom_projet}.")


def creer_regle_expéditeur(store, pid, metas, nom_projet):
    """Ranger un mail crée la règle du domaine de l'expéditeur."""
    domaine = metas.get("domaine", "")
    if not domaine:
        return None, None
    predicat = {"expediteur_contient": [domaine]}
    phrase = phrase_regle_expéditeur(domaine, nom_projet)
    rid = store.regle_add(pid, "mail", predicat, phrase)
    return rid, phrase


def creer_regle_dossier(store, pid, dossier, nom_projet):
    """La convention « un dossier par projet » devient une règle."""
    predicat = {"dossier": dossier}
    phrase = phrase_regle_dossier(dossier, nom_projet)
    rid = store.regle_add(pid, "dossier", predicat, phrase)
    return rid, phrase


def _mots(nom):
    """Mots significatifs d'un nom de projet ou de fichier."""
    return [m for m in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", nom.lower())
            if m not in TOKENS_SANS]


def suggerer_mail(store, objet):
    """Suggestion déterministe, avec son explication.

    Priorité : même expéditeur qu'un mail déjà rangé dans un projet,
    puis les mots du nom de projet trouvés dans l'objet du mail.
    """
    metas = json.loads(objet["metas"] or "{}")
    domaine = metas.get("domaine", "")
    if domaine:
        row = store.db.execute(
            "SELECT a.projet_id, p.nom, COUNT(*) n FROM attribution a"
            " JOIN objet o ON o.id=a.objet_id JOIN projet p ON p.id=a.projet_id"
            " WHERE o.type='mail' AND o.metas LIKE ?"
            " GROUP BY a.projet_id ORDER BY n DESC LIMIT 1",
            (f'%"{domaine}"%',)).fetchone()
        if row and row["n"] >= 2:
            return row["projet_id"], (
                f"Même expéditeur que {row['n']} mails de ce projet")
        if row and row["n"] == 1:
            return row["projet_id"], "Cet expéditeur a déjà écrit à ce projet"
    # mots du nom de projet dans l'objet du mail
    objet_mail = metas.get("objet", "").lower()
    for p in store.projets(etat="actif"):
        for mot in _mots(p["nom"]):
            if mot in objet_mail:
                return p["id"], f"L'objet du mail contient « {mot} »"
    return None, "Aucune règle ne s'applique"


def suggerer_fichier(store, objet):
    """Mots du nom de projet trouvés dans le nom du fichier."""
    nom = (objet["titre"] or "").lower()
    for p in store.projets(etat="actif"):
        for mot in _mots(p["nom"]):
            if mot in nom:
                return p["id"], f"Le nom du fichier contient « {mot} »"
    return None, "Aucune règle ne s'applique"
