"""Load an explicitly selected private env file before importing app settings."""

from pathlib import Path

from dotenv import load_dotenv


def load_private_env(path):
    if path is not None:
        selected = Path(path)
        if not selected.is_file():
            raise ValueError("Environment file is missing")
        load_dotenv(selected, override=True)
