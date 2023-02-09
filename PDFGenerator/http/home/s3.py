import subprocess
from collections import defaultdict
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from decouple import config

DELIMITER = "/"
FOLDERS_TO_IGNORE = {"Fichiers_communs"}
PUBLIC_DOWNLOADS_AVAILABILITY = 60 * 60 * 24  # 1 day

# S3 constants from env
S3_BUCKET_REFERENTIEL_PREPARATION = config("S3_BUCKET_REFERENTIEL_PREPARATION")
S3_BUCKET_REFERENTIEL_PRODUCTION = config("S3_BUCKET_REFERENTIEL_PRODUCTION")
S3_BUCKET_GENERATED_PRODUCTION = config("S3_BUCKET_GENERATED_PRODUCTION")
S3_BUCKET_COPYRIGHTED_SOURCES = config("S3_BUCKET_COPYRIGHTED_SOURCES")
S3_ENDPOINT = config("S3_ENDPOINT")
HOME_GENERATION_PATH = Path(config("HOME_GENERATION_PATH"))
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")


def list_ouvrages_en_preparation():
    client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=S3_ENDPOINT,
    )
    paginator = client.get_paginator("list_objects_v2")
    page = paginator.paginate(
        Bucket=S3_BUCKET_REFERENTIEL_PREPARATION,
        Delimiter=DELIMITER,
    )

    ouvrages = {
        s3_object["Prefix"].removesuffix(DELIMITER)
        for ouvrage_folders in page
        for s3_object in ouvrage_folders["CommonPrefixes"]
    }

    return sorted(ouvrages - FOLDERS_TO_IGNORE)


def get_document(ouvrage_name: str):
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=S3_ENDPOINT,
    )
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET_REFERENTIEL_PREPARATION,
                "Key": f"{ouvrage_name}/xml/document.xml",
            },
            ExpiresIn=300,
        )
    except ClientError as e:
        return None
    return response


def list_generated_documents_by_ouvrages():
    s3_resource = boto3.resource(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=S3_ENDPOINT,
    )
    bucket = s3_resource.Bucket(S3_BUCKET_GENERATED_PRODUCTION)

    ouvrages = defaultdict(lambda: defaultdict(dict))

    for s3_object in bucket.objects.all():
        key_path = Path(s3_object.key)
        ouvrage = key_path.parent.name
        file = key_path.name
        date = s3_object.last_modified
        presigned_url = s3_resource.meta.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET_GENERATED_PRODUCTION,
                "Key": s3_object.key,
            },
            ExpiresIn=PUBLIC_DOWNLOADS_AVAILABILITY,
        )

        ouvrages[ouvrage][file] = {"date": date, "url": presigned_url}

    ouvrages = {
        ouvrage_name: files
        for ouvrage_name, files in ouvrages.items()
        if "document.pdf" in files
    }

    return ouvrages


# fmt: off
COPYRIGHTED_SOURCES_FILES = {
    "licenses/saxon-license.lic": Path("/PDFGenerator") / "vendors" / "saxon" / "saxon-license.lic",
    "licenses/AHFormatter.lic": Path("/usr") / "AHFormatterV6_64" / "etc" / "AHFormatter.lic",
}
# fmt: on

COPYRIGHTED_SOURCES_DIRECTORIES = {
    "fonts": Path("/usr") / "AHFormatterV6_64" / "fonts",
}


def _s3_cp(s3_path, destination_path, recursive=False):
    recusive_params = ["--recursive"] if recursive else []
    subprocess.run(
        [
            "python",
            "-m",
            "awscli",
            "s3",
            "cp",
            *recusive_params,
            "--endpoint-url",
            S3_ENDPOINT,
            f"s3://{S3_BUCKET_COPYRIGHTED_SOURCES}/{s3_path}",
            str(destination_path),
        ],
        check=True,
    )


def _s3_sync(s3_path, destination_path):
    subprocess.run(
        [
            "python",
            "-m",
            "awscli",
            "s3",
            "sync",
            "--delete",
            "--endpoint-url",
            S3_ENDPOINT,
            f"s3://{S3_BUCKET_REFERENTIEL_PRODUCTION}/{s3_path}",
            destination_path,
        ],
        check=True,
    )


def _bootstrap_copyrighted_assets(
    copyrighted_sources_files, copyrighted_sources_directories
):
    for s3_path, destination_path in copyrighted_sources_files.items():
        if not destination_path.exists():
            # Using recursive=True to copy a single file messes that file encoding
            # We get an "Invalid encoding for signature" error from Saxon
            _s3_cp(s3_path, destination_path)

    for s3_path, destination_path in copyrighted_sources_directories.items():
        if destination_path.is_dir() and not any(destination_path.iterdir()):
            _s3_cp(s3_path, destination_path, recursive=True)


def _bootstrap_shom_assets():
    folders_to_sync = ["commun", "source"]
    for folder_name in folders_to_sync:
        _s3_sync(folder_name, HOME_GENERATION_PATH / folder_name)


def bootstrap_assets(
    copyrighted_sources_files=COPYRIGHTED_SOURCES_FILES,
    copyrighted_sources_directories=COPYRIGHTED_SOURCES_DIRECTORIES,
):
    _bootstrap_copyrighted_assets(
        copyrighted_sources_files, copyrighted_sources_directories
    )
    _bootstrap_shom_assets()


def _get_last_modified_by_ouvrage_based_on_subpath(bucket_name, file_subpath_to_match):
    s3_resource = boto3.resource(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=S3_ENDPOINT,
    )
    bucket = s3_resource.Bucket(bucket_name)
    last_modified_by_ouvrage = {}
    for file in bucket.objects.all():
        try:
            ouvrage, file_subpath = file.key.split("/", maxsplit=1)
        except ValueError:
            pass
        else:
            if file_subpath == file_subpath_to_match:
                last_modified_by_ouvrage[ouvrage] = file.last_modified

    return last_modified_by_ouvrage


def get_generated_pdf_ouvrages():
    return _get_last_modified_by_ouvrage_based_on_subpath(
        S3_BUCKET_GENERATED_PRODUCTION, "document.pdf"
    )


def get_source_xml_ouvrages():
    return _get_last_modified_by_ouvrage_based_on_subpath(
        S3_BUCKET_REFERENTIEL_PRODUCTION, "xml/document.xml"
    )
