import os
import uuid

from dotenv import load_dotenv

load_dotenv()

_AK = os.getenv("AK")
_SK = os.getenv("SK")
_ENDPOINT = os.getenv("ENDPOINT")
_BUCKET = os.getenv("BUCKET_NAME")

_obs_client = None


def _get_client():
    global _obs_client
    if _obs_client is None:
        from obs import ObsClient

        _obs_client = ObsClient(
            access_key_id=_AK,
            secret_access_key=_SK,
            server=_ENDPOINT,
        )
    return _obs_client


def upload_image(file_bytes: bytes, filename: str, username: str) -> str:
    """Upload image to OBS. Returns public URL."""
    ext = os.path.splitext(filename)[1] or ".jpg"
    object_key = f"{username}/{uuid.uuid4().hex}{ext}"

    client = _get_client()
    client.putObject(
        bucketName=_BUCKET,
        objectKey=object_key,
        content=file_bytes,
    )

    return f"https://{_BUCKET}.{_ENDPOINT}/{object_key}"
