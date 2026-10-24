"""projet — la ligne de commande ProjectOS.

Les verbes du dossier de conception : lister, ouvrir, ranger, sas,
règles, signet. Chaque sortie s'explique ; rien n'est appliqué
silencieusement.
"""

import argparse
import json
import os
import sys

from .collectors import scan_courrier, scan_fichiers
from .rules import (creer_regle_dossier, creer_regle_expéditeur,
                    suggerer_fichier, suggerer_mail)


def _store(args):
    from .store import Store
    return Store(os.path.expanduser(args.db))


def _resoudre_projet(store, ref):
    """Un projet se désigne par son id ou par son nom."""
    p = store.projet(ref) or store.projet_par_nom(ref)
    if not p:
        sys.exit(f"Projet inconnu : {ref}")
    return p


# ------------------------------------------------------------------ commandes

def cmd_scan(store, args):
    racine = os.path.abspath(args.racine)
    sf = scan_fichiers(store, racine)
    sc = {"nouveaux": 0, "total": 0}
    if args.courrier:
        sc = scan_courrier(store, args.courrier)
    print(f"Fichiers : {sf['total']} vus, {sf['nouveaux']} nouveaux,"
          f" {sf['deplaces']} retrouvés après renommage.")
    print(f"Courrier : {sc['total']} mails vus, {sc['nouveaux']} nouveaux.")


def cmd_list(store, args):
    print()
    print("PROJETS")
    for p in store.projets(etat="actif"):
        n = store.db.execute(
            "SELECT COUNT(*) FROM attribution WHERE projet_id=?",
            (p["id"],)).fetchone()[0]
        print(f"  {p['id']}  {p['nom']} — {n} objets"
              + (f" · échéance {p['echeance']}" if p["echeance"] else ""))
    pause = store.projets(etat="en_pause")
    if pause:
        print("EN PAUSE")
        for p in pause:
            print(f"  {p['id']}  {p['nom']}")
    print()


def cmd_create(store, args):
    pid = store.projet_create(args.nom, profil=args.profil,
                              dossier=os.path.abspath(args.dossier)
                              if args.dossier else None)
    p = store.projet(pid)
    print(f"Projet créé : {pid} · {p['nom']}")
    if args.dossier:
        rid, phrase = creer_regle_dossier(
            store, pid, os.path.abspath(args.dossier), args.nom)
        print(f"Règle : {phrase}")


def cmd_sas(store, args):
    objets = store.objets_sans_projet()
    if not objets:
        print("Le sas est vide.")
        return
    print(f"\nLE SAS — {len(objets)} objet(s) attendent un projet."
          f" Validez une suggestion, ou choisissez « hors projet ».\n")
    for i, o in enumerate(objets, 1):
        print(f"{i}. [{o['type']}] {o['titre']}")
        if o["type"] == "mail":
            metas = json.loads(o["metas"] or "{}")
            print(f"   {metas.get('de', '')} · {metas.get('objet', '')[:60]}")
            pid, pourquoi = suggerer_mail(store, o)
        else:
            pid, pourquoi = suggerer_fichier(store, o)
        if pid:
            p = store.projet(pid)
            print(f"   → Ranger dans {p['nom']} ?  ({pourquoi})"
                  f"   [ranger : {p['id']}]")
        else:
            print(f"   → {pourquoi}   [ranger : <id-projet> | hp = hors projet]")
        print()


def cmd_ranger(store, args):
    o = store.objet(args.objet)
    if not o:
        sys.exit(f"Objet inconnu : {args.objet}")
    p = _resoudre_projet(store, args.projet)
    if not p:
        sys.exit(f"Projet inconnu : {args.projet}")
    store.attribute(o["id"], p["id"], "manuel")
    print(f"Rangé : « {o['titre'][:60]} » → {p['nom']}")
    if args.sans_regle:
        return
    if o["type"] == "mail":
        metas = json.loads(o["metas"] or "{}")
        rid, phrase = creer_regle_expéditeur(store, p["id"], metas, p["nom"])
        if phrase:
            print(f"Ce rangement ajoute une règle au projet :\n  {phrase}")
            print("Vous pourrez la modifier ou la retirer à tout moment."
                  " Chaque objet rangé par elle le dira.")
    else:
        print("Pour les fichiers, les règles naissent des dossiers de"
              " projet, déclarés à la création — jamais du hasard.")


def cmd_hp(store, args):
    """Hors projet : tout ne relève pas d'un projet, le système le respecte."""
    store.ranger_hors_projet(args.objet)
    print("Écarté du sas, sans projet. Rien n'est rangé de force.")


def cmd_regles(store, args):
    pid = None
    if args.projet:
        pid = _resoudre_projet(store, args.projet)["id"]
    regles = store.regles(pid=pid)
    if not regles:
        print("Aucune règle active.")
        return
    for r in regles:
        p = store.projet(r["projet_id"])
        print(f"  [{p['nom']}] {r['phrase']}")
    print()


def cmd_signet(store, args):
    p = _resoudre_projet(store, args.projet)
    if not p:
        sys.exit(f"Projet inconnu : {args.projet}")
    store.db.execute("UPDATE projet SET signet=? WHERE id=?",
                     (args.texte, p["id"]))
    store.db.commit()
    print(f"Signet laissé dans {p['nom']} : « {args.texte} »")


def cmd_open(store, args):
    from .store import maintenant
    p = _resoudre_projet(store, args.projet)
    if not p:
        sys.exit(f"Projet inconnu : {args.projet}")
    print(f"\n{p['nom'].upper()}"
          + (f" · ÉCHÉANCE {p['echeance']}" if p["echeance"] else ""))
    if p["signet"]:
        print(f"Votre signet : « {p['signet']} »")
    derniere = p["derniere_visite"]
    if derniere:
        recents = store.objets_du_projet(p["id"], apres=derniere)
        print(f"Depuis votre passage : {len(recents)} objet(s) modifié(s)")
        for o in recents[:5]:
            print(f"  · {o['titre'][:70]}")
    print()
    for type_, libelle in (("mail", "COURRIER"), ("fichier", "DOCUMENTS")):
        objs = store.objets_du_projet(p["id"], type_=type_)
        sans_main = sum(1 for o in objs if o["origine"] in ("regle", "connecteur"))
        print(f"{libelle} — {len(objs)} objets,"
              f" {sans_main} rangés sans intervention")
        for o in objs[:6]:
            note = {"regle": "rangé par une règle",
                    "connecteur": "rattaché par le dossier du projet",
                    "manuel": "rangé à la main"}.get(o["origine"], o["origine"])
            print(f"  · {o['titre'][:66]}  ({note})")
        if len(objs) > 6:
            print(f"  … et {len(objs) - 6} autres")
        print()
    # boucles ouvertes : mails attribués au projet, sans réponse depuis N jours
    boucles = store.db.execute(
        "SELECT o.* FROM objet o JOIN attribution a ON a.objet_id=o.id"
        " WHERE a.projet_id=? AND o.type='mail' AND o.metas LIKE '%\"de\":%'"
        " ORDER BY o.modifie_le DESC LIMIT 50", (p["id"],)).fetchall()
    store.marquer_visite(p["id"])


def cmd_search(store, args):
    rows = store.rechercher(args.q, args.projet)
    print(f"\n{len(rows)} objet(s) pour « {args.q} » :")
    for o in rows:
        print(f"  · [{o['type']}] {o['titre'][:70]}")
    print()


def cmd_pause(store, args):
    p = _resoudre_projet(store, args.projet)
    store.db.execute("UPDATE projet SET etat='en_pause' WHERE id=?", (p["id"],))
    store.db.commit()
    print(f"{p['nom']} est en pause. Tout est gardé ; il reprendra à l'identique.")


def cmd_reprendre(store, args):
    p = _resoudre_projet(store, args.projet)
    store.db.execute("UPDATE projet SET etat='actif' WHERE id=?", (p["id"],))
    store.db.commit()
    print(f"{p['nom']} est de retour, tel qu'il a été laissé.")


def cmd_clore(store, args):
    p = _resoudre_projet(store, args.projet)
    boucles = [
        o for o in store.objets_du_projet(p["id"], type_="mail")[:50]]
    print(f"Bilan de clôture de {p['nom']} :")
    print(f"  · {len(store.objets_du_projet(p['id']))} objets, dont"
          f" {len(boucles)} mails")
    store.db.execute("UPDATE projet SET etat='archive' WHERE id=?", (p["id"],))
    store.db.commit()
    print("  · Le registre reste consultable et cherchable dans les archives.")


# ------------------------------------------------------------------ analyseur

def main():
    ap = argparse.ArgumentParser(
        prog="projet", description="ProjectOS — le projet d'abord.")
    ap.add_argument("--db", default="~/.projectos/index.db")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="collecter fichiers et courrier")
    s.add_argument("--racine", default=".")
    s.add_argument("--courrier", default=None)
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("list", help="lister les projets"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("creer", help="créer un projet")
    s.add_argument("nom"); s.add_argument("--profil", default="atelier")
    s.add_argument("--dossier", default=None); s.set_defaults(fn=cmd_create)

    s = sub.add_parser("sas", help="ce qui attend un projet"); s.set_defaults(fn=cmd_sas)

    s = sub.add_parser("ranger", help="rattacher un objet à un projet")
    s.add_argument("objet"); s.add_argument("projet")
    s.add_argument("--sans-regle", action="store_true")
    s.set_defaults(fn=cmd_ranger)

    s = sub.add_parser("hors-projet", help="écarter un objet du sas")
    s.add_argument("objet"); s.set_defaults(fn=cmd_hp)

    s = sub.add_parser("regles", help="les règles, en phrases")
    s.add_argument("projet", nargs="?", default=None); s.set_defaults(fn=cmd_regles)

    s = sub.add_parser("signet", help="laisser une note de reprise")
    s.add_argument("projet"); s.add_argument("texte"); s.set_defaults(fn=cmd_signet)

    s = sub.add_parser("ouvrir", help="reprendre un projet")
    s.add_argument("projet"); s.set_defaults(fn=cmd_open)

    s = sub.add_parser("chercher", help="recherche plein texte")
    s.add_argument("q"); s.add_argument("--projet", default=None)
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("pause", help="replier un projet")
    s.add_argument("projet"); s.set_defaults(fn=cmd_pause)
    s = sub.add_parser("reprendre", help="sortir un projet de pause")
    s.add_argument("projet"); s.set_defaults(fn=cmd_reprendre)
    s = sub.add_parser("clore", help="bilan de clôture puis archives")
    s.add_argument("projet"); s.set_defaults(fn=cmd_clore)

    args = ap.parse_args()
    args.fn(_store(args), args)


if __name__ == "__main__":
    main()
