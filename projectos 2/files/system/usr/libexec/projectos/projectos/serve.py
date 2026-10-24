"""etablid — le service de session, JSON-RPC 2.0 sur socket Unix.

Fidèle à l'architecture : l'API est locale, servie sur une socket du
répertoire runtime de l'utilisateur ; aucune passerelle réseau.
"""

import json
import os
import socket
import socketserver
import sys

from .rules import creer_regle_expéditeur, suggerer_fichier, suggerer_mail


def _faire_methodes(store):
    def methodes(nom, params):
        if nom == "projet.list":
            return [{"id": p["id"], "nom": p["nom"], "etat": p["etat"]}
                    for p in store.projets()]
        if nom == "projet.open":
            p = store.projet_par_nom(params["projet"]) \
                or store.projet(params["projet"])
            if not p:
                raise ValueError("projet inconnu")
            objets = [dict(o) for o in store.objets_du_projet(p["id"])]
            store.marquer_visite(p["id"])
            return {"projet": dict(p), "objets": objets}
        if nom == "sas.list":
            out = []
            for o in store.objets_sans_projet():
                pid, pourquoi = (suggerer_mail(store, o) if o["type"] == "mail"
                                 else suggerer_fichier(store, o))
                out.append({"id": o["id"], "type": o["type"],
                            "titre": o["titre"], "suggestion": pid,
                            "explication": pourquoi})
            return out
        if nom == "objet.ranger":
            o = store.objet(params["objet"])
            p = store.projet_par_nom(params["projet"]) \
                or store.projet(params["projet"])
            if not o or not p:
                raise ValueError("objet ou projet inconnu")
            store.attribute(o["id"], p["id"], params.get("origine", "manuel"))
            if o["type"] == "mail" and not params.get("sans_regle"):
                metas = json.loads(o["metas"] or "{}")
                _, phrase = creer_regle_expéditeur(store, p["id"], metas, p["nom"])
                return {"ok": True, "regle_creee": phrase}
            return {"ok": True}
        if nom == "regle.list":
            return [{"projet": r["projet_id"], "phrase": r["phrase"]}
                    for r in store.regles()]
        if nom == "objet.search":
            pid = None
            if params.get("projet"):
                p = store.projet_par_nom(params["projet"]) \
                    or store.projet(params["projet"])
                pid = p["id"] if p else None
            return [{"id": o["id"], "type": o["type"], "titre": o["titre"]}
                    for o in store.rechercher(params["q"], pid)]
        raise ValueError(f"méthode inconnue : {nom}")
    return methodes


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for ligne in self.rfile:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                req = json.loads(ligne)
                resultat = self.server.methodes(req.get("method"),
                                                 req.get("params", {}))
                reponse = {"jsonrpc": "2.0", "id": req.get("id"),
                           "result": resultat}
            except Exception as e:
                reponse = {"jsonrpc": "2.0", "id": req.get("id"),
                           "error": {"code": -32000, "message": str(e)}}
            self.wfile.write(json.dumps(reponse, ensure_ascii=False)
                             .encode() + b"\n")


def servir(chemin_db, chemin_sock=None):
    from .store import Store
    store = Store(chemin_db)
    chemin_sock = chemin_sock or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "projectos.sock")
    if os.path.exists(chemin_sock):
        os.unlink(chemin_sock)

    serveur = socketserver.UnixStreamServer(chemin_sock, Handler)
    serveur.methodes = _faire_methodes(store)
    os.chmod(chemin_sock, 0o600)  # l'utilisateur, et personne d'autre
    print(f"etablid écoute sur {chemin_sock}", file=sys.stderr)
    serveur.serve_forever()


if __name__ == "__main__":
    servir(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1
                              else "~/.projectos/index.db"),
           sys.argv[2] if len(sys.argv) > 2 else None)
