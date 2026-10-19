from pathlib import Path
import os
import re

from app.core.config import settings

KEY = re.compile(r"(?:staging/[0-9a-f]{32}\.part|objects/[0-9a-f]{32}\.(?:mp4|mov|webm))\Z")


class LocalStorage:
    def __init__(self, root=None):
        self.root = Path(root or settings.media_root).resolve()

    def path(self, key: str):
        if not KEY.fullmatch(key):
            raise ValueError("Invalid private storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Private storage path escaped root")
        return path

    def staging_key(self, final_key):
        self.path(final_key)
        return "staging/" + Path(final_key).stem + ".part"

    def create(self, key):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open("xb")

    def finalize(self, staging_key, final_key):
        source, target = self.path(staging_key), self.path(final_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError("Storage key already exists")
        os.replace(source, target)

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

    def exists(self, key):
        return self.path(key).is_file()

    def candidates(self):
        for directory in ("staging", "objects"):
            parent = self.root / directory
            if parent.is_dir():
                for path in parent.iterdir():
                    key = directory + "/" + path.name
                    if KEY.fullmatch(key) and not path.is_symlink() and path.is_file():
                        yield key, path.stat().st_mtime
