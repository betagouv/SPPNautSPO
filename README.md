# SPPNaut

Modernisation de la chaîne de production des publications nautiques

Ce projet est open-source sous license EUPL

## Installer et exécuter SPPNaut et le générateur de PDF sur un poste local

### Pré-requis

-   Docker
-   Docker-compose

En développement, copier le template des variables d'environnement

```sh
cd PDFGenerator/http
cp .env.template .env
```

Dans les autres environnements, prenez exemple sur le fichier `.env.template` pour configurer vos variables d'environnement sur l'environnement d'execution.

La base de données est utilisée pour l'administration des tâches déléguées par la librairie `procrastinate`.

### Variables d'environnements

Initialiser les 3 variables d'environnement suivantes dans le fichier [.env](PDFGenerator/http/.env) :

-   S3_BUCKET_GENERATED_PRODUCTION
-   AWS_ACCESS_KEY_ID
-   AWS_SECRET_ACCESS_KEY

### Readme PDFGenerator/http

Suivre les instructions du fichier [Readme](PDFGenerator/http/README.md) incluses dans PDFGenerator/http.

### Readme referentiel-sync

Le cas échéant, suivre les instructions du fichier [Readme](referentiel-sync/README.md).

### Exécution

Builder

```sh
docker-compose build
```

Executer

```sh
docker-compose up
```

L'interface est accessible sur [http://localhost:8080](http://localhost:8080)

Afficher les logs

```sh
docker-compose logs -f
```

## Pour générer un ouvrage sans SPPNautInterface

Démarrer le serveur :

```sh
docker-compose build
docker-compose up
```

Pour générer une publication :

```sh
docker-compose exec sppnaut mkdir -p <publication_path>
docker-compose exec sppnaut /PDFGenerator/http/bin/generator.py <publication_path> --s3_endpoint <S3_ENDPOINT> --s3_source_path s3://<S3_BUCKET_REFERENTIEL_PREPARATION>/<ouvrage>
```

Le `publication_path` include le nom de l'ouvrage et est le dossier dans lequel le document sera généré.

Le fichier pdf est disponible dans le dossier relatif calculé à partir de `publication_path`.

## Collecte des licenses des dépendances utilisées par nos applicatifs

On utilise pip-licenses: comme décrit sur le projet [SPPNauInterface](https://github.com/betagouv/SPPNautInterface/#readme)

# Services utilisés par l'équipe de développement

-   DNS: Alwaysdata
-   Hébergement: [Clever-cloud](https://console.clever-cloud.com/organisations/orga_975d316a-c00e-4fbb-b880-b5e79d58329b/members)
-   Fiche beta.gouv
-   Github: [Équipe SPPNaut](https://github.com/orgs/betagouv/teams/sppnaut)
-   Google Drive: https://drive.google.com/drive/folders/1t2FNI6_Le-Bv2UVrN0njTFt792vJASJK
-   Matomo: https://stats.data.gouv.fr
-   Sentry: https://sentry.incubateur.net

# Procrastinate

Les taches asynchrones de génération d'ouvrage sont prises en charge par la librairie procrastinate.

le lancement des workers est effectué dans le script [services.sh](./PDFGenerator/http/services.sh).

Le schema de la base de données est initialisée par ce même script lors de la première execution.

## Tâches d'administration

Pour ré-initialiser la liste de tâches planifiées :

```bash
PGPASSWORD=sppnaut psql --username sppnaut --dbname sppnaut --port 5434 -h localhost
```

```sql
DELETE FROM procrastinate_jobs;
```

Migration de la base de données liée à procrastinate :
voir la doc https://procrastinate.readthedocs.io/en/stable/howto/migrations.html

## Lancement "manuel" de la tache periodique

Sur le serveur executant procrastinate,

```bash
PYTHONPATH=. procrastinate --app=workers.procrastinate_app defer home.tasks.generate_all_updated_ouvrage_from_production '{"timestamp": 0}'
```

Pour les développeurs utilisant docker-compose

```bash
docker-compose exec --env PYTHONPATH=. sppnaut  procrastinate --app=workers.procrastinate_app defer home.tasks.generate_all_updated_ouvrage_from_production '{"timestamp": 0}'
```
