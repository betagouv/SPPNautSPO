import os
from unittest import mock
from unittest.mock import DEFAULT, patch

import boto3
import pytest
import time_machine
from django.conf import settings
from home.s3 import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    S3_BUCKET_GENERATED_PRODUCTION,
    S3_BUCKET_REFERENTIEL_PRODUCTION,
    S3_ENDPOINT,
)
from home.tasks import (
    generate_all_updated_ouvrage_from_production,
    generate_publication_from_referentiel,
)
from moto import mock_s3
from workers import procrastinate_app

os.environ["MOTO_S3_CUSTOM_ENDPOINTS"] = S3_ENDPOINT


@pytest.fixture
def mock_home_generation_path(tmp_path):
    with mock.patch.dict(os.environ, {"HOME_GENERATION_PATH": str(tmp_path)}):
        yield


class TestGeneratePublicationFromReferentiel:
    async def test_basic(self, tmp_path, mock_home_generation_path):
        with patch("home.tasks.generate", autospec=True) as generate_mock:
            await generate_publication_from_referentiel(
                ouvrage="g4",
                s3_endpoint="https://endpoint.fake",
                s3_inputs_bucket="bucket_fake",
                s3_source_path="s3://source_path_fake",
                s3_destination_path="s3://destination_path_fake",
            )

            assert len(list(tmp_path.iterdir())) == 1
            dir = list(tmp_path.iterdir())[0]
            assert list(dir.iterdir()) == [dir / "g4"]

            generate_mock.assert_awaited_once_with(
                dir / "g4",
                s3_endpoint="https://endpoint.fake",
                s3_inputs_bucket="bucket_fake",
                s3_source_path="s3://source_path_fake",
                s3_destination_path="s3://destination_path_fake",
                compress=True,
                vignette=True,
                metadata=True,
                cleanup=True,
            )

    async def test_new_folder_for_each_generation(
        self, tmp_path, mock_home_generation_path
    ):
        with patch("home.tasks.generate", autospec=True):
            await generate_publication_from_referentiel(
                ouvrage="g4",
                s3_endpoint="https://endpoint.fake",
                s3_inputs_bucket="bucket_fake",
                s3_source_path="s3://source_path_fake",
                s3_destination_path="s3://destination_path_fake",
            )
            await generate_publication_from_referentiel(
                ouvrage="g4",
                s3_endpoint="https://endpoint.fake",
                s3_inputs_bucket="bucket_fake",
                s3_source_path="s3://source_path_fake",
                s3_destination_path="s3://destination_path_fake",
            )

            assert len(list(tmp_path.iterdir())) == 2
            for dir in tmp_path.iterdir():
                assert list(dir.iterdir()) == [dir / "g4"]


class TestGenerateAllUpdatedOuvrageFromProduction:
    @pytest.fixture
    def s3_resource(self):
        with mock_s3():
            yield boto3.resource(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                endpoint_url=S3_ENDPOINT,
            )

    @pytest.fixture
    def procrastinate(self):
        procrastinate_app.connector.reset()
        return procrastinate_app.connector

    @pytest.fixture
    def s3_bucket_generated_production(self, s3_resource):
        bucket = s3_resource.Bucket(S3_BUCKET_GENERATED_PRODUCTION)
        bucket.create()
        yield bucket

    @pytest.fixture
    def s3_bucket_referentiel_production(self, s3_resource):
        bucket = s3_resource.Bucket(S3_BUCKET_REFERENTIEL_PRODUCTION)
        bucket.create()
        yield bucket

    async def test_empty(
        self,
        s3_bucket_generated_production,
        s3_bucket_referentiel_production,
        procrastinate,
    ):
        await generate_all_updated_ouvrage_from_production(0)
        assert procrastinate.jobs == {}

    async def test_basic(
        self,
        s3_bucket_generated_production,
        s3_bucket_referentiel_production,
        procrastinate,
    ):
        with time_machine.travel("2022-01-01 11:00 +0000", tick=False) as traveller:
            s3_bucket_referentiel_production.put_object(
                Key="g4/xml/document.xml", Body=""
            )
            s3_bucket_generated_production.put_object(Key="g4/document.pdf", Body="")
            s3_bucket_generated_production.put_object(Key="11/document.pdf", Body="")
            s3_bucket_generated_production.put_object(Key="12/document.pdf", Body="")

            traveller.shift(60)
            s3_bucket_referentiel_production.put_object(
                Key="11/xml/document.xml", Body=""
            )
            s3_bucket_referentiel_production.put_object(
                Key="12/xml/document.xml", Body=""
            )

        await generate_all_updated_ouvrage_from_production(0)
        queued_jobs = list(procrastinate.jobs.values())

        for job in queued_jobs:
            assert job["task_name"] == "generate_publication_from_referentiel"
            assert job["status"] == "todo"

        assert {tuple(job["args"].items()) for job in queued_jobs} == {
            (
                ("ouvrage", "11"),
                ("s3_endpoint", settings.S3_ENDPOINT),
                (
                    "s3_inputs_bucket",
                    f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}",
                ),
                (
                    "s3_source_path",
                    f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}/11",
                ),
                (
                    "s3_destination_path",
                    f"s3://{settings.S3_BUCKET_GENERATED_PRODUCTION}/11",
                ),
            ),
            (
                ("ouvrage", "12"),
                ("s3_endpoint", settings.S3_ENDPOINT),
                (
                    "s3_inputs_bucket",
                    f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}",
                ),
                (
                    "s3_source_path",
                    f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}/12",
                ),
                (
                    "s3_destination_path",
                    f"s3://{settings.S3_BUCKET_GENERATED_PRODUCTION}/12",
                ),
            ),
        }

    async def test_no_pdf(
        self,
        s3_bucket_generated_production,
        s3_bucket_referentiel_production,
        procrastinate,
    ):
        s3_bucket_referentiel_production.put_object(Key="11/xml/document.xml", Body="")

        await generate_all_updated_ouvrage_from_production(0)
        queued_jobs = list(procrastinate.jobs.values())
        assert len(queued_jobs) == 1
        assert queued_jobs[0]["task_name"] == "generate_publication_from_referentiel"
        assert queued_jobs[0]["status"] == "todo"
        assert queued_jobs[0]["args"] == {
            "ouvrage": "11",
            "s3_endpoint": settings.S3_ENDPOINT,
            "s3_inputs_bucket": f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}",
            "s3_source_path": f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}/11",
            "s3_destination_path": f"s3://{settings.S3_BUCKET_GENERATED_PRODUCTION}/11",
        }

    async def test_no_xml(
        self,
        s3_bucket_generated_production,
        s3_bucket_referentiel_production,
        procrastinate,
    ):
        s3_bucket_generated_production.put_object(Key="g4/document.pdf", Body="")

        await generate_all_updated_ouvrage_from_production(0)
        assert procrastinate.jobs == {}

    async def test_multiple_xml(
        self,
        s3_bucket_generated_production,
        s3_bucket_referentiel_production,
        procrastinate,
    ):
        with time_machine.travel("2022-01-01 11:00 +0000", tick=False) as traveller:
            s3_bucket_referentiel_production.put_object(
                Key="11/tableau/xml/document.xml", Body=""
            )
            s3_bucket_generated_production.put_object(Key="11/document.pdf", Body="")

            traveller.shift(60)
            s3_bucket_referentiel_production.put_object(
                Key="11/xml/document.xml", Body=""
            )

        await generate_all_updated_ouvrage_from_production(0)
        queued_jobs = list(procrastinate.jobs.values())

        assert len(queued_jobs) == 1
