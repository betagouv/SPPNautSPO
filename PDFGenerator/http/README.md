## Installation avec pip-tools

Dans l'environnement virtuel de votre choix (python > 3.10), installez pip-tools

```sh
python -m pip install pip-tools
```

Les dépendances sont décrites dans `pyproject.toml`.

Pour générer les fichiers `requirements.txt` et `dev-requirements.txt`, recopiez les commandes indiqués dans l'entête de ces fichiers.

Puis installer les dépendances avec pip (nécessaire pour faire tourner les tests et les hooks de pre-commit)

```sh
pip install -r requirements.txt -r dev-requirements.txt
```

## Lancer l'interface

suivre les instructions dans le [README.md à la base du projet](../../README.md)
