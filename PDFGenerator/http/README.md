# PDFGenerator/http

Cette application backend assure la génération d'ouvrages.

Elle est basée sur :
-   [Django](https://www.djangoproject.com) pour le backend (+ Postgres)
-   [Procrastinate](https://www.djangoproject.com) pour l'execution de tâches de fond

## Pré-requis

Pour faire fonctionner l'interface en local, il est recommandé d'utiliser :

-   Python >= 3.10

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

## Exécution

Cette application est démarrée lors du démarrage de la stack Docker décrite dans le [README.md à la base du projet](../../README.md).  


### Pour générer un ouvrage sans SPPNautInterface

S'assurer que le serveur démarré précédemment est en cours d'execution.   
Depuis un autre shell : 

```sh
docker-compose exec sppnaut mkdir -p <publication_path>
docker-compose exec sppnaut /PDFGenerator/http/bin/generator.py <publication_path> --s3_endpoint <S3_ENDPOINT> --s3_source_path s3://<S3_BUCKET_REFERENTIEL_PREPARATION>/<ouvrage>
```

Le `publication_path` include le nom de l'ouvrage et est le dossier dans lequel le document sera généré.

Le fichier pdf est disponible dans le dossier relatif calculé à partir de `publication_path`.

## Interface

L'interface est séparée dans une autre application, dont l'installation et exécution sont décrites dans le [README.md à la base du projet](../../README.md).

## Procrastinate

Les tâches asynchrones de génération d'ouvrage sont prises en charge par la librairie procrastinate.  
le lancement des workers est effectué dans le script [services.sh](./services.sh).  
Le schéma de la base de données est initialisée par ce même script lors de la première execution.

### Tâches d'administration

Pour ré-initialiser la liste de tâches planifiées :

```bash
PGPASSWORD=sppnaut psql --username sppnaut --dbname sppnaut --port 5434 -h localhost
```

```sql
DELETE FROM procrastinate_jobs;
```

Migration de la base de données liée à procrastinate :
voir la doc https://procrastinate.readthedocs.io/en/stable/howto/migrations.html

### Lancement "manuel" de la tache périodique

Sur le serveur executant procrastinate :

```bash
PYTHONPATH=. procrastinate --app=workers.procrastinate_app defer home.tasks.generate_all_updated_ouvrage_from_production '{"timestamp": 0}'
```

Pour les développeurs utilisant docker-compose :

```bash
docker-compose exec --env PYTHONPATH=. sppnaut  procrastinate --app=workers.procrastinate_app defer home.tasks.generate_all_updated_ouvrage_from_production '{"timestamp": 0}'
```
