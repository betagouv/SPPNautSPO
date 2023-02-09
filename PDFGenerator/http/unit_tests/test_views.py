import logging
from base64 import b64encode

import pytest


@pytest.fixture
def authorization_header(settings):
    GENERATOR_USERNAME, GENERATOR_PASSWORD = list(settings.BASICAUTH_USERS.items())[0]
    return "Basic " + b64encode(
        bytes(
            f"{GENERATOR_USERNAME}:{GENERATOR_PASSWORD}",
            encoding="utf8",
        )
    ).decode("utf8")


class TestGeneratePublicationFromUpload:
    def test_basic(
        self,
        tmp_path,
        settings,
        client,
        authorization_header,
        fake_process,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)

        fake_generator = fake_process.register(
            [
                settings.BIN_DIR / "echo_returncode_in.py",
                fake_process.any(min=1, max=1),
                settings.BASE_DIR / "bin" / "generator.py",
                tmp_path / "fake_generation_id" / "g4p",
                "--s3_endpoint",
                "https://cellar-fr-north-hds-c1.services.clever-cloud.com",
                "--s3_inputs_bucket",
                f"s3://sppnaut-referentiel-production",
            ],
        )

        response = client.post(
            "/publication/fake_generation_id/generate",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert fake_generator.calls

        assert response.status_code == 202

    def test_multiple_ouvrages_in_generation(
        self, tmp_path, settings, client, authorization_header
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)
        (tmp_path / "fake_generation_id" / "g4z").mkdir(parents=True)

        response = client.post(
            "/publication/fake_generation_id/generate",
            HTTP_AUTHORIZATION=authorization_header,
        )
        assert response.status_code == 400


class TestGenerateFromProduction:
    @pytest.fixture
    def fake_g4_generator(self, fake_process, settings):
        return fake_process.register(
            [
                settings.BIN_DIR / "echo_returncode_in.py",
                fake_process.any(min=1, max=1),
                settings.BASE_DIR / "bin" / "generator.py",
                fake_process.any(min=1, max=1),
                "--s3_endpoint",
                "https://cellar-fr-north-hds-c1.services.clever-cloud.com",
                "--s3_inputs_bucket",
                f"s3://sppnaut-referentiel-production",
                "--s3_source_path",
                f"s3://sppnaut-referentiel-production/g4",
                "--s3_destination_path",
                f"s3://S3_BUCKET_GENERATED_PRODUCTION/g4",
                "--compress",
                "--vignette",
                "--metadata",
            ],
        )

    def test_http(
        self,
        tmp_path,
        settings,
        client,
        fake_g4_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_production/generate",
            {"ouvrage": "g4"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert fake_g4_generator.calls
        assert response.status_code == 202
        assert "generation_id" in response.json()

    def test_filesystem_setup(
        self,
        tmp_path,
        settings,
        client,
        fake_g4_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_production/generate",
            {"ouvrage": "g4"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        generation_id = response.json()["generation_id"]
        assert fake_g4_generator.calls
        assert (tmp_path / generation_id / "g4").exists()

    def test_shell_script_options(
        self,
        tmp_path,
        settings,
        client,
        fake_g4_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_production/generate",
            {"ouvrage": "g4"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        generation_id = response.json()["generation_id"]
        publication_path = tmp_path / generation_id / "g4"
        assert fake_g4_generator.first_call.args[1] == publication_path / "returncode"
        assert fake_g4_generator.first_call.args[3] == publication_path


class TestGenerateFromPreparation:
    @pytest.fixture
    def fake_g4p_generator(self, fake_process, settings):
        return fake_process.register(
            [
                settings.BIN_DIR / "echo_returncode_in.py",
                fake_process.any(min=1, max=1),
                settings.BASE_DIR / "bin" / "generator.py",
                fake_process.any(min=1, max=1),
                "--s3_endpoint",
                "https://cellar-fr-north-hds-c1.services.clever-cloud.com",
                "--s3_inputs_bucket",
                "s3://sppnaut-referentiel-production",
                "--s3_source_path",
                f"s3://sppnaut-referentiel-preparation/g4p",
            ],
        )

    def test_http(
        self,
        tmp_path,
        settings,
        client,
        fake_g4p_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_preparation/generate",
            {"ouvrage": "g4p"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert fake_g4p_generator.calls
        assert response.status_code == 202
        assert "generation_id" in response.json()

    def test_filesystem_setup(
        self,
        tmp_path,
        settings,
        client,
        fake_g4p_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_preparation/generate",
            {"ouvrage": "g4p"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        generation_id = response.json()["generation_id"]
        assert fake_g4p_generator.calls

        assert (tmp_path / generation_id / "g4p").exists()

    def test_shell_script_options(
        self,
        tmp_path,
        settings,
        client,
        fake_g4p_generator,
        authorization_header,
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        response = client.post(
            "/publication/from_preparation/generate",
            {"ouvrage": "g4p"},
            HTTP_AUTHORIZATION=authorization_header,
        )

        generation_id = response.json()["generation_id"]
        publication_path = tmp_path / generation_id / "g4p"
        assert fake_g4p_generator.first_call.args[1] == publication_path / "returncode"
        assert fake_g4p_generator.first_call.args[3] == publication_path


class TestPublication:
    def test_no_sign_of_generation(self, client, authorization_header):
        response = client.get(
            "/publication/inexistant_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 409

    def test_generation_not_started(
        self, tmp_path, settings, client, authorization_header
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)

        response = client.get(
            "/publication/fake_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 404
        assert response.content.decode() == "Démarrage…"
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    def test_generation_in_progress(
        self, tmp_path, settings, client, authorization_header
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)
        (tmp_path / "fake_generation_id" / "g4p" / "displayable_step").write_text(
            "Trop bieng!"
        )

        response = client.get(
            "/publication/fake_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 404
        assert response.content.decode() == "Trop bieng!"
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    def test_generation_failed(
        self, tmp_path, settings, client, authorization_header, caplog
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)
        (tmp_path / "fake_generation_id" / "g4p" / "returncode").write_text("1")
        (tmp_path / "fake_generation_id" / "g4p" / "stderr.log").write_text(
            """Oh noes!
Many errors!
Traceback (most recent call last):
  File "generator.py", line 302, in <module>
    generate(**vars(args))
"""
        )

        response = client.get(
            "/publication/fake_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 500
        assert response.content.decode() == "Oh noes!\nMany errors!"
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        assert caplog.record_tuples == [
            ("root", logging.WARNING, "Oh noes!"),
            ("root", logging.WARNING, "Many errors!"),
            ("root", logging.WARNING, "Traceback (most recent call last):"),
            ("root", logging.WARNING, '  File "generator.py", line 302, in <module>'),
            ("root", logging.WARNING, "    generate(**vars(args))"),
            ("root", logging.ERROR, "Publication g4p failed to generate"),
            (
                "django.request",
                logging.ERROR,
                "Internal Server Error: /publication/fake_generation_id/",
            ),
        ]

    def test_generation_done(self, tmp_path, settings, client, authorization_header):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)
        (tmp_path / "fake_generation_id" / "g4p" / "returncode").write_text("0")
        (tmp_path / "fake_generation_id" / "g4p" / "document.pdf").write_text("abcd")

        response = client.get(
            "/publication/fake_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 200
        assert response.filename == "g4p.pdf"
        assert response.headers["content-type"] == "application/pdf"
        assert list(response.streaming_content) == [b"abcd"]

    def test_calmar_generation_done(
        self, tmp_path, settings, client, authorization_header
    ):
        settings.HOME_GENERATION_PATH = tmp_path

        (tmp_path / "fake_generation_id" / "g4p").mkdir(parents=True)
        (tmp_path / "fake_generation_id" / "g4p" / "returncode").write_text("0")
        (tmp_path / "fake_generation_id" / "g4p" / "archive.zip").write_text("abcd")

        response = client.get(
            "/publication/fake_generation_id/",
            HTTP_AUTHORIZATION=authorization_header,
        )

        assert response.status_code == 200
        assert response.filename == "g4p.zip"
        assert response.headers["content-type"] == "application/zip"
        assert list(response.streaming_content) == [b"abcd"]
