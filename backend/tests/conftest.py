import os
from pathlib import Path

# Make TEST_DATABASE_URL from backend/.env visible to the tests (real env vars win).
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())
