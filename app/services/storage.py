from pathlib import Path
import os
import re
from contextlib import contextmanager
import hashlib
import tempfile
from uuid import uuid4

from app.core.config import settings

KEY = re.compile(
    r"(?:staging/[0-9a-f]{32}\.part|objects/[0-9a-f]{32}\.(?:mp4|mov|webm))\Z"
)


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

    def check(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=self.root) as probe:
            probe.write(b"readiness")
            probe.flush()

    def size(self, key):
        return self.path(key).stat().st_size

    def open_range(self, key, start, end):
        return self.path(key).open("rb")

    @contextmanager
    def materialize(self, key, *, checksum=None, progress=None):
        yield self.path(key)


class StorageUnavailable(OSError):
    """Safe error: SDK messages may contain signed URLs or credentials."""


class RangeBody:
    def __init__(self, body, start):
        self.body, self.start = body, start

    def seek(self, offset):
        if offset != self.start:
            raise ValueError("Range stream cannot seek")

    def read(self, size):
        try:
            return self.body.read(size)
        except Exception:
            raise StorageUnavailable("Object storage read failed") from None

    def close(self):
        self.body.close()


class B2Storage:
    def __init__(self, client=None):
        self.bucket = settings.b2_bucket
        if client is not None:
            self.client = client
            return
        if not all((self.bucket, settings.b2_key_id, settings.b2_application_key)):
            raise StorageUnavailable("Object storage configuration incomplete")
        from urllib.parse import urlsplit

        endpoint = urlsplit(settings.b2_endpoint_url)
        if (
            endpoint.scheme != "https"
            or endpoint.username
            or endpoint.password
            or endpoint.hostname != f"s3.{settings.b2_region}.backblazeb2.com"
            or endpoint.path not in ("", "/")
            or endpoint.query
            or endpoint.fragment
        ):
            raise StorageUnavailable("Invalid B2 endpoint")
        import boto3
        from botocore.config import Config

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.b2_endpoint_url,
            region_name=settings.b2_region,
            aws_access_key_id=settings.b2_key_id,
            aws_secret_access_key=settings.b2_application_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=15,
                retries={"max_attempts": 2},
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def _call(self, operation, **kwargs):
        try:
            return getattr(self.client, operation)(Bucket=self.bucket, **kwargs)
        except FileNotFoundError:
            raise
        except Exception as error:
            code = getattr(error, "response", {}).get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError("Object not found") from None
            raise StorageUnavailable("Object storage operation failed") from None

    def validate(self, key):
        if not KEY.fullmatch(key):
            raise ValueError("Invalid private storage key")
        return key

    def staging_key(self, final_key):
        self.validate(final_key)
        return "staging/" + Path(final_key).stem + ".part"

    def head(self, key):
        return self._call("head_object", Key=self.validate(key))

    def size(self, key):
        return self.head(key)["ContentLength"]

    def exists(self, key):
        try:
            self.head(key)
            return True
        except FileNotFoundError:
            return False

    def presign(self, key, size, mime, seconds):
        try:
            return self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": self.validate(key),
                    "ContentLength": size,
                    "ContentType": mime,
                },
                ExpiresIn=seconds,
                HttpMethod="PUT",
            )
        except Exception:
            raise StorageUnavailable("Object storage signing failed") from None

    def finalize_version(self, source, target, version):
        # Copy a pinned version: a reused PUT URL cannot change accepted media.
        if not version or version == "null":
            raise StorageUnavailable("Object version is required")
        self._call(
            "copy_object",
            Key=self.validate(target),
            CopySource={
                "Bucket": self.bucket,
                "Key": self.validate(source),
                "VersionId": version,
            },
        )

    def delete(self, key):
        self.validate(key)
        # B2 keeps versions. Delete actual versions, including late PUT replays,
        # rather than merely adding a delete marker.
        for page in self._version_pages(key):
            for item in page.get("Versions", []) + page.get("DeleteMarkers", []):
                if item["Key"] == key:
                    self._call("delete_object", Key=key, VersionId=item["VersionId"])

    def _version_pages(self, prefix):
        params = {"Prefix": prefix, "MaxKeys": 1000}
        while True:
            page = self._call("list_object_versions", **params)
            yield page
            if not page.get("IsTruncated"):
                return
            params.update(
                KeyMarker=page["NextKeyMarker"],
                VersionIdMarker=page["NextVersionIdMarker"],
            )

    def candidates(self):
        for prefix in ("staging/", "objects/"):
            for page in self._version_pages(prefix):
                for item in page.get("Versions", []) + page.get("DeleteMarkers", []):
                    if KEY.fullmatch(item["Key"]):
                        yield item["Key"], item["LastModified"].timestamp()

    def open_range(self, key, start, end):
        result = self._call(
            "get_object", Key=self.validate(key), Range=f"bytes={start}-{end}"
        )
        return RangeBody(result["Body"], start)

    @contextmanager
    def materialize(self, key, *, checksum=None, progress=None):
        result = self._call("get_object", Key=self.validate(key))
        body = result["Body"]
        reader = RangeBody(body, 0)
        try:
            with tempfile.TemporaryDirectory(prefix="silatsense-") as folder:
                target = Path(folder) / Path(key).name
                size, digest = 0, hashlib.sha256()
                with target.open("wb") as handle:
                    while chunk := reader.read(256 * 1024):
                        size += len(chunk)
                        if size > settings.max_video_mb * 1024 * 1024:
                            raise ValueError("Video exceeds size limit")
                        digest.update(chunk)
                        handle.write(chunk)
                        if progress:
                            progress()
                if size != result["ContentLength"] or (
                    checksum and digest.hexdigest() != checksum
                ):
                    raise ValueError("Video checksum or length mismatch")
                yield target
        finally:
            body.close()

    def check(self):
        key = f"staging/{uuid4().hex}.part"
        try:
            self._call("put_object", Key=key, Body=b"readiness")
            result = self._call("get_object", Key=key)
            try:
                if result["Body"].read(10) != b"readiness":
                    raise StorageUnavailable("Object storage probe failed")
            finally:
                result["Body"].close()
        finally:
            self.delete(key)


def get_storage():
    return B2Storage() if settings.storage_adapter == "b2" else LocalStorage()
