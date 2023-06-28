# referentiel-sync

## Synchronisation totale : partage réseau SHOM > S3

### Variables d'environnement

Définir les variables d'environnement :

```
HTTP_PROXY=http://squid.shom.fr:3128
HTTPS_PROXY=http://squid.shom.fr:3128
```

Copier le fichier `.env.template` vers `.env`.

### Installation

```
python -m venv .venv --prompt referentiel-sync
.venv\Scripts\activate
pip install -r requirements.txt --proxy http://squid.shom.fr:3128
```

Configurer les "AWS Access Key ID" et "AWS Secret Access Key" avec la commande suivante:

```
python -m awscli configure
```

Configurer la version de signature du protocole S3 avec la commande suivante:

```
python -m awscli configure set default.s3.signature_version s3
```

### Execution

#### Synchronisation complète

Attention: pensez à préciser le sous dossier `referentiel` dans l'option `referentiel_local_path` pour que le contenu du référentiel soit synchronisé sans la mention `referentiel` dans le chemin S3.

```
python full_sync.py <local_path> <s3_bucket_name>
```

Exemple :

```
python full_sync.py \\samba\DATA\referentiel sppnaut-referentiel
```

#### Synchronisation incrémentale

Attention: pensez à préciser le sous dossier "referentiel" dans l'option referentiel_local_path pour que le contenu du référentiel soit synchronisé sans la mention "referentiel" dans le chemin S3.

```
python incremental_sync.py <local_path> <s3_bucket_name>
```

Exemple :

```
python incremental_sync.py \\samba\DATA\\referentiel sppnaut-referentiel
```
