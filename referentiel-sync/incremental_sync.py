"""
Watch a folder to incrementally synchronise it to S3
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from stat import filemode

import sentry_sdk
from decouple import config
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_fixed)
from watchdog.events import LoggingEventHandler, PatternMatchingEventHandler
from watchdog.observers import Observer

S3_ENDPOINT = config("S3_ENDPOINT")
SENTRY_DSN = config("SENTRY_DSN")
INCLUDE_PATTERNS = config(
    "INCLUDE_PATTERNS", cast=lambda v: [s.strip() for s in v.split(",")]
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.info("File watcher launched...")


sentry_sdk.init(
    dsn=SENTRY_DSN,
)


class S3UploadHandler(PatternMatchingEventHandler):
    """
    Uploads any matching file in S3.

    This does the simplest thing possible by uploading files.
    Removing files from S3 because they've been deleted or renamed is the responsibility of `full_sync.py`.
    """

    def __init__(self, s3_bucket, referentiel_local_path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.s3_bucket = s3_bucket
        self.referentiel_local_path = referentiel_local_path.resolve()

    def _build_s3_path(self, path: Path) -> str:
        relative_path = PurePosixPath(
            path.resolve().relative_to(self.referentiel_local_path)
        )
        return f"s3://{self.s3_bucket}/{relative_path}"

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(.2),
        retry=retry_if_exception_type(subprocess.CalledProcessError),
        reraise=True,
    )
    def _upload(self, file_to_upload: str) -> None:
        path_to_upload = Path(file_to_upload)
        if not path_to_upload.exists():
            logging.info("File does not exist, skipping: %s", path_to_upload)
            return
        if not any(path_to_upload.match(pattern) for pattern in INCLUDE_PATTERNS):
            logging.info("File does not match patterns, skipping: %s", path_to_upload)
            return

        awscli = subprocess.run(
            [
                sys.executable,
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                S3_ENDPOINT,
                str(path_to_upload),
                self._build_s3_path(path_to_upload),
            ],
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
        )
        logging.info("AWSCLI: %s", awscli.stdout.decode())

        try:
            awscli.check_returncode()
        except subprocess.CalledProcessError:
            if "Skipping file" in awscli.stdout.decode():
                # AWS can't read the file
                # we skip it until the next Ffile system notification
                # when the file will be available.
                logging.warning("Skipping file: %s", path_to_upload)
                return

            raise


    def dispatch(self, event):
        # We don't want failing commands to crash our process. So we just report exceptions.
        try:
            super().dispatch(event)
        except Exception as e:
            logging.exception(e)

    def on_created(self, event):
        self._upload(event.src_path)

    def on_modified(self, event):
        self._upload(event.src_path)

    def on_moved(self, event):
        self._upload(event.dest_path)


parser = argparse.ArgumentParser()
parser.add_argument("referentiel_local_path", type=Path)
parser.add_argument("s3_bucket", help="Bucket name (without s3://)")
args = parser.parse_args()

path = args.referentiel_local_path
log_handler = LoggingEventHandler()
s3_storage_handler = S3UploadHandler(
    args.s3_bucket,
    args.referentiel_local_path,
    patterns=INCLUDE_PATTERNS,
    ignore_directories=True,
)
observer = Observer()
observer.schedule(s3_storage_handler, path, recursive=True)
observer.schedule(log_handler, path, recursive=True)
observer.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
