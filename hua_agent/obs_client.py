"""OBS image upload client — singleton connection pool."""

import os
import threading
import uuid

from obs import ObsClient

_client: ObsClient | None = None
_bucket: str = ""
_endpoint: str = ""
_lock = threading.Lock()


def init_obs(ak: str, sk: str, endpoint: str, bucket: str) -> None:
    """Initialize OBS client at application startup."""
    global _client, _bucket, _endpoint
    with _lock:
        _client = ObsClient(
            access_key_id=ak,
            secret_access_key=sk,
            server=endpoint,
        )
        _bucket = bucket
        _endpoint = endpoint


def upload_image(file_bytes: bytes, filename: str, username: str) -> str:
    """Upload image to OBS. Returns public URL."""
    ext = os.path.splitext(filename)[1] or ".jpg"
    object_key = f"{username}/{uuid.uuid4().hex}{ext}"

    if _client is None:
        raise RuntimeError("OBS client not initialized — call init_obs() at startup")

    _client.putObject(
        bucketName=_bucket,
        objectKey=object_key,
        content=file_bytes,
    )
    return f"https://{_bucket}.{_endpoint}/{object_key}"
