#!/usr/bin/env python
import subprocess
import sys
from pathlib import Path

completed_process = subprocess.run(sys.argv[2:])
Path(sys.argv[1]).write_text(str(completed_process.returncode))
