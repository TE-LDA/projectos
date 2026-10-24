"""projetd — prototype du service ProjectOS.

Le cœur du système : un magasin d'objets unique (SQLite), où chaque
objet — fichier, mail — porte une identité invariante (UUID) et des
attributions à des projets. L'empreinte et l'inode ne sont que des
indices de récupération, jamais des identités.
"""

__version__ = "0.1.0"
