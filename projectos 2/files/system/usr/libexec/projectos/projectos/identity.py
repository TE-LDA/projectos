"""Identité des objets.

L'identité d'un fichier est un UUID attribué à la première indexation,
inscrit en attribut étendu et dans l'index. Elle ne change jamais.
L'inode et l'empreinte ne servent qu'à retrouver un fichier devenu
introuvable (renommé, déplacé) — jamais à le définir.

Chaînage, du plus fiable au plus résilient :
1. xattr   — l'UUID est lu dans le fichier même ;
2. inode   — le fichier a été renommé ou déplacé ;
3. empreinte + taille — en dernier recours, et seulement si
   l'ancienne localisation n'existe plus : la même pièce jointe
   enregistrée deux fois reste deux objets distincts.
"""

import hashlib
import os
import uuid

XATTR = "user.projectos.id"


def empreinte(path, taille_bloc=1 << 16):
    """BLAKE2b du contenu (blake3 non disponible partout) + taille."""
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        while True:
            bloc = f.read(taille_bloc)
            if not bloc:
                break
            h.update(bloc)
    st = os.stat(path)
    return h.hexdigest(), st.st_size


def lire_uuid_xattr(path):
    try:
        return os.getxattr(path, XATTR).decode()
    except OSError:
        return None


def inscrire_uuid_xattr(path, oid):
    """Le marquage xattr est une optimisation, pas une dépendance."""
    try:
        os.setxattr(path, XATTR, oid.encode())
        return True
    except OSError:
        return False


def identite_fichier(store, path):
    """Retourne (uuid | None, commentaire). Rien n'est écrit dans l'index."""
    # 1. xattr
    oid = lire_uuid_xattr(path)
    if oid and store.objet(oid):
        return oid, "identité lue dans l'attribut étendu"
    # 2. inode + taille (renommé / déplacé)
    st = os.stat(path)
    row = store.db.execute(
        "SELECT id FROM objet WHERE inode=? AND taille=? AND type='fichier'",
        (st.st_ino, st.st_size)).fetchone()
    if row:
        return row["id"], "retrouvé par inode (renommé ou déplacé)"
    # 3. empreinte + taille, si l'ancienne localisation a disparu
    emp, taille = empreinte(path)
    row = store.db.execute(
        "SELECT id, localisation FROM objet"
        " WHERE empreinte=? AND taille=?", (emp, taille)).fetchone()
    if row and (row["localisation"] is None
                or not os.path.exists(row["localisation"])):
        return row["id"], "retrouvé par empreinte (contenu identique)"
    return None, None


def identite_mail(compte, message_id, metas):
    """Le courrier : couple (compte, Message-ID), avec repli sur un
    hachage des en-têtes si le Message-ID manque ou est dupliqué."""
    if message_id:
        return f"mail:{compte}:{message_id}"
    amorce = f"{metas.get('de','')}|{metas.get('date','')}|{metas.get('objet','')}"
    return "mail:{}:{}".format(compte, hashlib.blake2b(
        amorce.encode(), digest_size=10).hexdigest())
