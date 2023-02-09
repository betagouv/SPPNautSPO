"""
Synchronize a folder to S3
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import sentry_sdk
from decouple import config

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
logging.info("File sync launched...")

sentry_sdk.init(
    dsn=SENTRY_DSN,
)


include_arguments = []
for pattern in INCLUDE_PATTERNS:
    include_arguments.append("--include")
    include_arguments.append(pattern)

    # We add **/ because it seems to be necessary to ignore these patterns in subdirectories
    include_arguments.append("--include")
    include_arguments.append(f"**/{pattern}")

parser = argparse.ArgumentParser()
parser.add_argument("referentiel_local_path")
parser.add_argument("s3_bucket")
args = parser.parse_args()

if not Path(args.referentiel_local_path).is_dir():
    logging.error(
        "The directory being synced cannot be found - %s",
        args.referentiel_local_path,
    )
    exit(1)

subprocess.run(
    [
        sys.executable,
        "-m",
        "awscli",
        "s3",
        "sync",
        args.referentiel_local_path,
        f"s3://{args.s3_bucket}",
        "--delete",
        "--endpoint-url",
        S3_ENDPOINT,
        "--exclude",
        "*"
        # "--debug",
    ]
    + include_arguments,
    check=True,
)
