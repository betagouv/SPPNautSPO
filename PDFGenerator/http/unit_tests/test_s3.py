import os
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
import time_machine
from home.s3 import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    HOME_GENERATION_PATH,
    S3_BUCKET_COPYRIGHTED_SOURCES,
    S3_BUCKET_GENERATED_PRODUCTION,
    S3_BUCKET_REFERENTIEL_PREPARATION,
    S3_BUCKET_REFERENTIEL_PRODUCTION,
    S3_ENDPOINT,
    bootstrap_assets,
    get_generated_pdf_ouvrages,
    list_generated_documents_by_ouvrages,
    list_ouvrages_en_preparation,
)
from moto import mock_s3

os.environ["MOTO_S3_CUSTOM_ENDPOINTS"] = S3_ENDPOINT

BOTO_MAX_KEYS_DEFAULT = 1000


@pytest.fixture
def s3_resource():
    with mock_s3():
        yield boto3.resource(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            endpoint_url=S3_ENDPOINT,
        )


class TestListOuvragesEnPreparation:
    @pytest.fixture
    def s3_bucket_referentiel_preparation(self, s3_resource):
        bucket = s3_resource.Bucket(S3_BUCKET_REFERENTIEL_PREPARATION)
        bucket.create()
        yield bucket

    def test_basic(self, s3_bucket_referentiel_preparation):
        for key in ["g4/document.xml", "11/document.xml", "a2/document.xml"]:
            s3_bucket_referentiel_preparation.put_object(Key=key, Body="")

        ouvrages = list_ouvrages_en_preparation()
        assert ouvrages == ["11", "a2", "g4"]

    def test_no_fichiers_communs(self, s3_bucket_referentiel_preparation):
        for key in [
            "g4/document.xml",
            "11/document.xml",
            "Fichiers_communs/document.xml",
        ]:
            s3_bucket_referentiel_preparation.put_object(Key=key, Body="")

        ouvrages = list_ouvrages_en_preparation()
        assert ouvrages == ["11", "g4"]

    def test_only_folders(self, s3_bucket_referentiel_preparation):
        for key in ["g4/document.xml", "11/document.xml", "ignore_me.txt"]:
            s3_bucket_referentiel_preparation.put_object(Key=key, Body="")

        ouvrages = list_ouvrages_en_preparation()
        assert ouvrages == ["11", "g4"]

    @pytest.mark.slow
    def test_many_folders(self, s3_bucket_referentiel_preparation):
        for i in range(BOTO_MAX_KEYS_DEFAULT + 1):
            s3_bucket_referentiel_preparation.put_object(
                Key=f"{i}/document.xml", Body=""
            )

        assert len(list_ouvrages_en_preparation()) == BOTO_MAX_KEYS_DEFAULT + 1


class TestListGeneratedDocumentsByOuvrages:
    @pytest.fixture
    def s3_bucket_generated_production(self, s3_resource):
        bucket = s3_resource.Bucket(S3_BUCKET_GENERATED_PRODUCTION)
        bucket.create()
        yield bucket

    def test_basic(self, s3_bucket_generated_production):
        for key in [
            "g4/document.pdf",
            "g4/vignette.jpg",
            "11/document.pdf",
            "11/vignette.jpg",
        ]:
            s3_bucket_generated_production.put_object(Key=key, Body="")

        ouvrages = list_generated_documents_by_ouvrages()
        assert ouvrages.keys() == {"g4", "11"}

        for ouvrage_name, ouvrage in ouvrages.items():
            assert ouvrage.keys() == {"document.pdf", "vignette.jpg"}

            for file_name, file in ouvrage.items():
                assert file.keys() == {"date", "url"}

                assert isinstance(file["date"], datetime)

                url = urlparse(file["url"])
                assert url.scheme == "https"
                assert url.path.endswith(ouvrage_name + "/" + file_name)

                query_string = parse_qs(url.query)
                tomorrow = datetime.now() + timedelta(days=1)
                assert abs(int(query_string["Expires"][0]) - tomorrow.timestamp()) < 10

    @pytest.mark.slow
    def test_many_objects(self, s3_bucket_generated_production):
        for i in range(BOTO_MAX_KEYS_DEFAULT + 1):
            s3_bucket_generated_production.put_object(Key=f"{i}/document.pdf", Body="")
        assert (
            len(list_generated_documents_by_ouvrages().keys())
            == BOTO_MAX_KEYS_DEFAULT + 1
        )

    def test_only_folder_with_document_pdf(self, s3_bucket_generated_production):
        for key in [
            "g4/document.pdf",
            "c5/bogus.pdf",
            "c6/document.bug",
        ]:
            s3_bucket_generated_production.put_object(Key=key, Body="")

        ouvrages = list_generated_documents_by_ouvrages()
        assert ouvrages.keys() == {"g4"}


class TestBootstrapAssets:
    @pytest.fixture
    def fake_s3_copy_commun(self, fake_process):
        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_commun_path = f"s3://{S3_BUCKET_REFERENTIEL_PRODUCTION}/commun"
        return fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "sync",
                "--delete",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_commun_path,
                HOME_GENERATION_PATH / "commun",
            ],
            stderr=["AWS sync commun"],
        )

    @pytest.fixture
    def fake_s3_copy_source(self, fake_process):
        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_source_path = f"s3://{S3_BUCKET_REFERENTIEL_PRODUCTION}/source"
        return fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "sync",
                "--delete",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_source_path,
                HOME_GENERATION_PATH / "source",
            ],
            stderr=["AWS sync source"],
        )

    def test_downloads_if_no_file(
        self, tmp_path, fake_s3_copy_commun, fake_s3_copy_source, fake_process
    ):
        COPYRIGHTED_SOURCES_FILES = {"foo_s3": tmp_path / "foo"}

        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_source_path = f"s3://{S3_BUCKET_COPYRIGHTED_SOURCES}/foo_s3"
        fake_copyrighted_assets = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_source_path,
                str(tmp_path / "foo"),
            ]
        )

        bootstrap_assets(COPYRIGHTED_SOURCES_FILES, {})

        assert fake_s3_copy_commun.calls
        assert fake_s3_copy_source.calls

        assert fake_copyrighted_assets.calls

    def test_downloads_if_directory_empty(
        self, tmp_path, fake_s3_copy_commun, fake_s3_copy_source, fake_process
    ):
        COPYRIGHTED_SOURCES_DIRECTORIES = {"foo_s3": tmp_path / "foo"}

        (tmp_path / "foo").mkdir()

        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_source_path = f"s3://{S3_BUCKET_COPYRIGHTED_SOURCES}/foo_s3"
        fake_copyrighted_assets = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--recursive",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_source_path,
                str(tmp_path / "foo"),
            ]
        )

        bootstrap_assets({}, COPYRIGHTED_SOURCES_DIRECTORIES)

        assert fake_s3_copy_commun.calls
        assert fake_s3_copy_source.calls

        assert fake_copyrighted_assets.calls

    def test_no_download_if_file_exists(
        self, tmp_path, fake_s3_copy_commun, fake_s3_copy_source, fake_process
    ):
        COPYRIGHTED_SOURCES_FILES = {"foo_s3": tmp_path / "foo"}

        (tmp_path / "foo").touch()

        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_source_path = f"s3://{S3_BUCKET_COPYRIGHTED_SOURCES}/foo_s3"
        fake_copyrighted_assets = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_source_path,
                str(tmp_path / "foo"),
            ]
        )

        bootstrap_assets(COPYRIGHTED_SOURCES_FILES, {})

        assert fake_s3_copy_commun.calls
        assert fake_s3_copy_source.calls

        assert len(fake_copyrighted_assets.calls) == 0

    def test_no_download_if_directory_not_empty(
        self, tmp_path, fake_s3_copy_commun, fake_s3_copy_source, fake_process
    ):
        COPYRIGHTED_SOURCES_DIRECTORIES = {"foo_s3": tmp_path / "foo"}

        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "bar").touch()

        fake_s3_endpoint = S3_ENDPOINT
        fake_s3_source_path = f"s3://{S3_BUCKET_COPYRIGHTED_SOURCES}/foo_s3"
        fake_copyrighted_assets = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_s3_source_path,
                str(tmp_path / "foo"),
            ]
        )

        bootstrap_assets({}, COPYRIGHTED_SOURCES_DIRECTORIES)

        assert fake_s3_copy_commun.calls
        assert fake_s3_copy_source.calls

        assert len(fake_copyrighted_assets.calls) == 0
