"""
Synchronize a folder to S3
"""

import argparse
import logging
import subprocess
import sys

from decouple import config

S3_ENDPOINT = config("S3_ENDPOINT")
INCLUDE_PATTERNS = config(
    "INCLUDE_PATTERNS", cast=lambda v: [s.strip() for s in v.split(",")]
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.info("File sync launched...")

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
