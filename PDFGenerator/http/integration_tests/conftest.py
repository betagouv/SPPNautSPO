import subprocess
import time
from pathlib import Path

import pytest
import requests

INTEGRATION_TESTS_ROOT = Path(__file__).parent
DOTENV_FILE = INTEGRATION_TESTS_ROOT.parent / ".env"
DOTENV_TEST_FILE = INTEGRATION_TESTS_ROOT.parent / ".env.test"


@pytest.fixture(scope="session")
def ds_server():
    assert DOTENV_FILE.exists()
    ds_proc = subprocess.Popen(
        [
            "docker",
            "run",
            "--env-file",
            DOTENV_FILE,
            "--env-file",
            DOTENV_TEST_FILE,
            "--rm",
            "--publish",
            "8081:8080",
            "sppnaut_sppnaut",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # Give the server time to start
    time.sleep(1)
    # Check it started successfully
    assert not ds_proc.poll(), ds_proc.stdout.read().decode("utf-8")

    max_retries = 5
    # Wait for the HTTP server to be available
    for attempt in range(1, max_retries + 1):
        try:
            requests.get("http://localhost:8081/health_check/")
        except requests.ConnectionError:
            print(f"{attempt} of {max_retries}: HTTP server not ready.")
            if attempt < max_retries:
                print("Retrying in one second")
            time.sleep(1)
        else:
            print("HTTP server ready")
            break

    yield ds_proc
    # Shut it down at the end of the pytest session
    ds_proc.terminate()
    # Log Docker stdout to help debug failing tests
    print(ds_proc.stdout.read().decode("utf-8"))
