import hashlib
import time
import uuid
from pathlib import Path

import requests
from decouple import Config, RepositoryEnv

INTEGRATION_TESTS_ROOT = Path(__file__).parent

DOTENV_FILE = INTEGRATION_TESTS_ROOT.parent / ".env.template"
env_config = Config(RepositoryEnv(DOTENV_FILE))


def test_health_check_unauthorized(ds_server):
    response = requests.get("http://localhost:8081/health_check/")
    assert response.status_code == 401


def test_health_check_successful(ds_server):
    username = env_config("BASICAUTH_USERS_USERNAME")
    password = env_config("BASICAUTH_USERS_PASSWORD")
    response = requests.get(
        "http://localhost:8081/health_check/", auth=(username, password)
    )
    assert response.status_code == 200


def test_table_generation(ds_server):
    username = env_config("BASICAUTH_USERS_USERNAME")
    password = env_config("BASICAUTH_USERS_PASSWORD")
    response = requests.post(
        "http://localhost:8081/",
        files={
            "file": (INTEGRATION_TESTS_ROOT / "fixtures" / "ing4_0.2.6.xml").open("rb")
        },
        auth=(username, password),
    )
    # We need to limit to 10000 char because of creation and modification date
    # which is updated at each generation
    CONTENT_LIMIT_BEFORE_TIME_MENTIONED_IN_PDF = 10000
    tableau_md5 = hashlib.md5(
        response.content[:CONTENT_LIMIT_BEFORE_TIME_MENTIONED_IN_PDF]
    ).hexdigest()

    assert response.status_code == 200
    assert tableau_md5 == "ef0c931396349353bf96c8d72a3de552"


def test_generate_minimal_ouvrage_via_upload(ds_server):
    username = env_config("BASICAUTH_USERS_USERNAME")
    password = env_config("BASICAUTH_USERS_PASSWORD")

    fake_generation_id = uuid.uuid4()
    upload_response = requests.post(
        f"http://localhost:8081/publication/{fake_generation_id}/upload_input",
        files={
            "file": (
                INTEGRATION_TESTS_ROOT
                / "fixtures"
                / "minimal_ouvrage"
                / "xml"
                / "document.xml"
            ).open("rb")
        },
        data={"webkitRelativePath": "minimal_ouvrage/xml/document.xml"},
        auth=(username, password),
    )

    assert upload_response.status_code == 202

    generate_response = requests.post(
        f"http://localhost:8081/publication/{fake_generation_id}/generate",
        auth=(username, password),
    )
    assert generate_response.status_code == 202

    while True:
        ouvrage_response = requests.get(
            f"http://localhost:8081/publication/{fake_generation_id}/",
            auth=(username, password),
        )

        if ouvrage_response.status_code != 404:
            # Generation finished
            break

        print(ouvrage_response.text)
        time.sleep(3)

    assert ouvrage_response.status_code == 200
    assert ouvrage_response.headers["content-type"] == "application/pdf"

    assert (
        ouvrage_response.headers["content-disposition"]
        == 'inline; filename="minimal_ouvrage.pdf"'
    )
