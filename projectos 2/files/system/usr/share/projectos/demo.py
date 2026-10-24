"""Scénario de démonstration : une journée de Hélène, pour de vrai.

Construit un espace de travail avec fichiers et courrier, puis déroule
le fil des maquettes : le sas, les suggestions, les règles créées par
les rangements, la survie de l'identité au renommage, le signet et la
reprise. Tout passe par la ligne de commande `projet` : rien n'est
simulé dans ce script.

Usage :  python3 demo.py            (recrée l'espace de travail à zéro)
"""

import json
import os
import shutil
import subprocess
import sys
import textwrap

ICI = os.path.dirname(os.path.abspath(__file__))
TRAVAIL = os.path.join(ICI, "workspace")
DB = os.path.join(TRAVAIL, "index.db")
RACINE = os.path.join(TRAVAIL, "documents")
COURRIER = os.path.join(TRAVAIL, "courrier")

CLI = [sys.executable, "-m", "projectos.cli", "--db", DB]
ENV = dict(os.environ, PYTHONPATH=ICI)


def etape(titre):
    print("\n" + "─" * 72)
    print("■ " + titre)
    print("─" * 72)


def projet(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True,
                       cwd=TRAVAIL, env=ENV)
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)
    return r.stdout


def _mail(path, de, objet, corps, date="Tue, 03 Nov 2026"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"From: {de}\nSubject: {objet}\nDate: {date}\n"
                f"Message-ID: <{os.path.basename(path)}@demo>\n"
                f"Content-Type: text/plain; charset=utf-8\n\n{corps}\n")


def creer_donnees():
    if os.path.exists(TRAVAIL):
        shutil.rmtree(TRAVAIL)
    for d in ("documents/Duval", "documents/Rapport annuel",
              "documents/telechargements", "courrier/Boite/cur",
              "courrier/Boite/new"):
        os.makedirs(os.path.join(TRAVAIL, d), exist_ok=True)
    # fichiers
    with open(os.path.join(RACINE, "Duval", "Plan_R+1_v4.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 plan des bureaux R+1, revision 4")
    with open(os.path.join(RACINE, "Duval", "CCTP_lot3.docx"), "wb") as f:
        f.write(b"PK\x03\x04 CCTP lot 3 - electricite")
    with open(os.path.join(RACINE, "Rapport annuel", "chapitre2.md"),
              "w", encoding="utf-8") as f:
        f.write("# Chapitre 2 — le bilan des chantiers de l'année\n")
    with open(os.path.join(RACINE, "telechargements",
                           "Programme_salon_2026.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 programme du salon de l'habitat 2026")
    # courrier déjà traité par Hélène dans le projet Duval
    for i in (1, 2, 3):
        _mail(os.path.join(COURRIER, "Boite/cur", f"arcade{i}"),
              "etudes@arcade-be.fr", f"Note de calcul lot 3 ({i})",
              "Voici la note de calcul." * 3)
    # courrier du jour
    _mail(os.path.join(COURRIER, "Boite/cur", "duval1"),
          "Agnès Duval <agnes@duval.fr>", "Planning des travaux de décembre",
          "Pouvez-vous confirmer l'intervention de l'électricien ?")
    _mail(os.path.join(COURRIER, "Boite/cur", "duval2"),
          "Julien Morel <julien@duval.fr>", "Plan R+1 v4 : modifications",
          "J'ai repris la cloison du bureau 12.")
    _mail(os.path.join(COURRIER, "Boite/new", "facture1"),
          "facturation@arcade-be.fr", "Facture d'acompte n° 2026-114",
          "Veuillez trouver la facture d'acompte.")
    _mail(os.path.join(COURRIER, "Boite/new", "bat1"),
          "Imprimerie Vauban <bat@imprimerie-vauban.fr>",
          "Bon à tirer — rapport annuel 2026",
          "Le BAT du rapport annuel est prêt.")
    _mail(os.path.join(COURRIER, "Boite/new", "lettre1"),
          "Ordre des architectes <info@ordredesarchitectes.fr>",
          "Lettre d'information de novembre",
          "La lettre mensuelle.")


def pre_attribuer_arcade():
    """Hélène a déjà rangé trois mails d'Arcade dans Refonte Duval,
    à la main, sans créer de règle. Le quatrième arrivera au sas."""
    from projectos.store import Store
    store = Store(DB)
    rd = store.projet_par_nom("Refonte Duval")["id"]
    n = 0
    for o in store.db.execute(
            "SELECT id FROM objet WHERE type='mail' AND metas LIKE"
            " '%arcade-be.fr%' AND titre LIKE 'Note de calcul%'").fetchall():
        store.attribute(o["id"], rd, "manuel")
        n += 1
    print(f"(préparation : {n} mails d'Arcade déjà rangés dans"
          f" Refonte Duval, sans règle)")
    del n


def main():
    creer_donnees()

    etape("1 · Créer les projets — la convention « un dossier par projet »"
          " devient une règle")
    projet("creer", "Refonte Duval", "--dossier",
           os.path.join(RACINE, "Duval"))
    projet("creer", "Rapport annuel", "--dossier",
           os.path.join(RACINE, "Rapport annuel"))
    projet("creer", "Salon de l'habitat")

    etape("2 · Premier passage — les collecteurs lisent, ne déplacent rien")
    projet("scan", "--racine", RACINE, "--courrier", COURRIER)
    pre_attribuer_arcade()

    etape("3 · Le sas — chaque suggestion s'explique")
    projet("sas")

    etape("4 · Ranger — valider une suggestion crée une règle")
    # on range comme Hélène : duval1 (premier mail Duval), la facture
    # (même expéditeur), le BAT (mot du nom du projet), le programme du
    # salon (mot du nom) ; la lettre de l'Ordre reste hors projet.
    from projectos.store import Store
    store = Store(DB)
    duval1 = store.db.execute("SELECT id FROM objet WHERE titre LIKE"
                              " 'Planning%'").fetchone()["id"]
    projet("ranger", duval1, "Refonte Duval")
    print()
    facture = store.db.execute("SELECT id FROM objet WHERE titre LIKE"
                               " 'Facture%'").fetchone()["id"]
    projet("ranger", facture, "Refonte Duval")
    print()
    bat = store.db.execute("SELECT id FROM objet WHERE titre LIKE"
                           " 'Bon à tirer%'").fetchone()["id"]
    projet("ranger", bat, "Rapport annuel")
    print()
    programme = store.db.execute("SELECT id FROM objet WHERE titre LIKE"
                                 " 'Programme_salon%'").fetchone()["id"]
    projet("ranger", programme, "Salon de l'habitat")
    print()
    lettre = store.db.execute("SELECT id FROM objet WHERE titre LIKE"
                             " 'Lettre%'").fetchone()["id"]
    projet("hors-projet", lettre)

    etape("5 · Les règles, en phrases")
    projet("regles")

    etape("6 · Re-scanner : la règle duval.fr range le fil,"
          " sans intervention")
    projet("scan", "--racine", RACINE, "--courrier", COURRIER)
    duval2 = store.db.execute("SELECT * FROM objet WHERE titre LIKE"
                              " 'Plan R+1 v4%'").fetchone()
    att = store.attributions(duval2["id"])
    print(f"« {duval2['titre']} » : "
          + ", ".join(f"{a['nom']} (origine {a['origine']})" for a in att))

    etape("7 · L'épreuve : renommer et déplacer un fichier")
    chemin = os.path.join(RACINE, "Duval", "Plan_R+1_v4.pdf")
    nouveau = os.path.join(RACINE, "Duval", "Plan_R+1_final.pdf")
    os.rename(chemin, nouveau)
    shutil.move(nouveau, os.path.join(RACINE, "Duval", "archive_plan.pdf"))
    projet("scan", "--racine", RACINE, "--courrier", COURRIER)
    plan = store.db.execute("SELECT * FROM objet WHERE titre LIKE"
                            " 'archive_plan%'").fetchone()
    att = store.attributions(plan["id"])
    print(f"« {plan['titre']} », renommé puis déplacé — attributions : "
          + (", ".join(f"{a['nom']}" for a in att) if att else "PERDUES"))
    from projectos.identity import lire_uuid_xattr
    print(f"xattr lu dans le fichier : {lire_uuid_xattr(plan['localisation'])}"
          f"  (identité de l'index : {plan['id']})")

    etape("8 · Le signet, puis la reprise")
    projet("signet", "Refonte Duval",
           "Relancer le bureau d'études sur le devis électricité.")
    projet("ouvrir", "Refonte Duval")

    etape("8 bis · Un mail arrive pendant que vous êtes ailleurs")
    _mail(os.path.join(COURRIER, "Boite/new", "duval3"),
          "Agnès Duval <agnes@duval.fr>", "Confirmation de l'électricien",
          "L'électricien confirme son intervention pour la semaine 48.")
    projet("scan", "--racine", RACINE, "--courrier", COURRIER)
    projet("ouvrir", "Refonte Duval")

    etape("9 · Chercher — la recherche traverse les types et ignore les"
          " accents")
    # la requête est tapée SANS accents ; le FTS est alimenté en texte
    # sans accents : elle trouve « l'électricien » dans les mails.
    projet("chercher", "electricien")
    print()
    # et le contenu des fichiers texte est indexé aussi : « bilan »
    # est dans chapitre2.md. (PDF et .docx exigent des extracteurs,
    # hors périmètre du prototype : ils restent trouvables par titre.)
    projet("chercher", "bilan")

    print("\n" + "─" * 24 + " fin du scénario " + "─" * 24 + "\n")


if __name__ == "__main__":
    main()
