# ProjectOS

*Le système qui s'organise autour de vos projets.*

Ce dépôt fabrique la **distribution ProjectOS** : une image Linux construite
sur Fedora Atomic (via Universal Blue), mise à jour d'un bloc et réversible.

## Où en est-on

| Étape | Contenu | État |
| --- | --- | --- |
| 1 — L'image | Base Fedora Atomic, service `projetd`, commande `projet`, polices Spectral et Inter, couleurs et fonds ProjectOS, Firefox, Thunderbird, LibreOffice | **Dans ce dépôt** |
| 2 — Le bureau ProjectOS v0 | Interface plein écran (rail, Ma journée, sas, projet) lancée comme session | À venir |
| 3 — Interface branchée au cœur | Le bureau lit `projetd` par sa socket locale | À venir |
| 4 — Système conscient du projet | Portail de fichiers, scopes systemd, notifications par levées | À venir |
| 5 — Gestionnaire de fenêtres ProjectOS | Fenêtres rattachées aux projets, bascule de décor | Phase 1 |

## Comment l'image est construite

À chaque modification, GitHub construit l'image et la publie sur
`ghcr.io/te-lda/projectos:latest`. Tout est décrit dans
`recipes/recipe.yml` ; les fichiers ajoutés au système sont dans `files/`.

## L'essayer

Dans une machine virtuelle sous Fedora Silverblue (GNOME Boxes ou
VirtualBox), ouvrir un terminal et taper :

```
rpm-ostree rebase ostree-unverified-registry:ghcr.io/te-lda/projectos:latest
systemctl reboot
```

Au redémarrage, la commande `projet` est disponible et le service `projetd`
tourne. Pour revenir en arrière : `rpm-ostree rollback`.

L'image n'est pas encore signée (d'où « unverified ») : la signature
cosign est la prochaine étape d'infrastructure, avec la fabrication d'un
fichier ISO d'installation.
