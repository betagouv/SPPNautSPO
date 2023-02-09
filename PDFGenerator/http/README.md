## Installation avec pip-tools

Dans l'environnement virtuel de votre choix (python > 3.10), installez pip-tools

```sh
python -m pip install pip-tools
```

Les dépendances sont décrites dans `requirements.in` et `dev-requirements.in` pour les dépendences propres à l'environnement de dev (comme son nom l'indique). \

Générer les fichiers `requirements.txt` et `dev-requirements.txt`

```sh
pip-compile --generate-hashes requirements.in
pip-compile --generate-hashes dev-requirements.in
```

Puis installer les dépendances avec pip (nécessaire pour faire tourner les tests et les hooks de pre-commit)

```sh
pip install -r requirements.txt -r dev-requirements.txt
```

## Lancer l'interface

suivre les instructions dans le [README.md à la base du projet](../../README.md)
