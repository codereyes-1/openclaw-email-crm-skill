#!/usr/bin/env python3
"""Run a local, synthetic, no-transport v2 demonstration."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

parser = argparse.ArgumentParser()
parser.add_argument("--db", help="demo database; omitted creates a temporary database")
args = parser.parse_args()

temporary = tempfile.TemporaryDirectory() if not args.db else None
db = Path(args.db) if args.db else Path(temporary.name) / "demo.sqlite"
commands = [
    ["init_email_crm.py"],
    ["ingest_messages.py", "--adapter", "synthetic", "--input", str(ROOT / "fixtures" / "synthetic_messages.json")],
    ["brief_email_crm.py", "--json"],
]
for command in commands:
    result = subprocess.run([sys.executable, str(SCRIPTS / command[0]), "--db", str(db), *command[1:]], check=True, text=True, capture_output=True)
    print(result.stdout.strip())
print(f"Demo complete. transport_performed=false db={db}")
