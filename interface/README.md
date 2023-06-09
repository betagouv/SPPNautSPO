# SPPNaut

SPPNaut est une startup d'Etat dont la mission est la modernisaton et l'ouverture des publications nautiques.

## Dévéloppement

### Prerequis

Pour faire tourner l'interface en local, il est conseiller d'utiliser :

-   Python >= 3.10
-   docker et docker-compose pour faire tourner la base de données Postgresql (cf. [SPPNautGenerator](https://github.com/betagouv/SPPNautGenerator))

### Installation

1. Création et activation de votre environnement virtuel. Par exemple via ces commandes :

    ```sh
    python -m venv .venv --prompt $(basename $(pwd))
    source .venv/bin/activate
    ```

1. Installation des dépendances

    ```sh
    pip install pip-tools
    pip-sync requirements.txt dev-requirements.txt
    ```

1. Création des variables d'environnement

    En développement :

    ```sh
    cp .env.template .env
    ```

    Dans les autres environnements, prenez exemple sur le fichier `.env.template` pour configurer vos variables d'environnement sur l'environnement d'execution

1. Implémenter le schéma de la base de données

    `./manage.py migrate`

    La base de données est composée des tables d'administration de django pour assurer l'authentification

1. Installation des dépendances JS

    `npm install`

1. Lancement des serveurs de développement

    `honcho start`

    L'interface est disponible sur votre navigateur à l'adresse [http://localhost:8000](http://localhost:8000)
