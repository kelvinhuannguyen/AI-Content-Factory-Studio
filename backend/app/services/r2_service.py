"""Cloudflare R2 service — S3-compatible upload/download via boto3."""
import asyncio
import logging
import mimetypes
from functools import partial
from pathlib import Path

import boto3
from botocore.config import Config

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3_client


async def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to R2. Returns the R2 key."""
    if not settings.r2_account_id or not settings.r2_access_key_id:
        logger.warning("R2 not configured — skipping upload for key %s", key)
        return key

    loop = asyncio.get_event_loop()
    client = _get_client()
    await loop.run_in_executor(
        None,
        partial(
            client.put_object,
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        ),
    )
    logger.info("R2 upload OK: %s (%d bytes)", key, len(data))
    return key


async def upload_file(key: str, file_path: str | Path) -> str:
    """Upload a local file to R2 by path. Returns the R2 key."""
    if not settings.r2_account_id or not settings.r2_access_key_id:
        logger.warning("R2 not configured — skipping upload for %s", key)
        return key

    file_path = Path(file_path)
    content_type, _ = mimetypes.guess_type(str(file_path))
    content_type = content_type or "application/octet-stream"

    loop = asyncio.get_event_loop()
    client = _get_client()
    await loop.run_in_executor(
        None,
        partial(
            client.upload_file,
            str(file_path),
            settings.r2_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        ),
    )
    logger.info("R2 upload OK: %s", key)
    return key


async def download_bytes(key: str) -> bytes:
    """Download an object from R2 as bytes."""
    loop = asyncio.get_event_loop()
    client = _get_client()
    response = await loop.run_in_executor(
        None,
        partial(client.get_object, Bucket=settings.r2_bucket_name, Key=key),
    )
    return response["Body"].read()


def public_url(key: str) -> str | None:
    """Return the public URL for a key (if R2_PUBLIC_URL is set)."""
    if settings.r2_public_url:
        return f"{settings.r2_public_url.rstrip('/')}/{key}"
    return None


async def generate_presigned_url(key: str, expires: int = 3600) -> str:
    """Generate a pre-signed download URL valid for `expires` seconds."""
    loop = asyncio.get_event_loop()
    client = _get_client()
    url = await loop.run_in_executor(
        None,
        partial(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=expires,
        ),
    )
    return url
