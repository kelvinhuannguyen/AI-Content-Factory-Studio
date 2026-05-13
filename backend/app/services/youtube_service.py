"""YouTube Data API v3 — OAuth2 + resumable video upload."""
from __future__ import annotations
import asyncio
import io
import logging
from functools import partial
from pathlib import Path

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_CHUNK_SIZE = 256 * 1024   # 256 KB chunks for resumable upload


class YouTubeError(Exception):
    pass


def _get_service(credentials):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


async def upload_video(
    video_bytes: bytes,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "unlisted",   # "public" | "unlisted" | "private"
    credentials_json: str | None = None,
) -> str:
    """
    Upload MP4 video to YouTube via resumable upload.
    Returns the YouTube video ID on success.

    credentials_json: OAuth2 token JSON (user-authenticated, not service account).
    If not provided, tries to load from YOUTUBE_CLIENT_* env vars flow.
    """
    if not credentials_json and not settings.youtube_client_id:
        raise YouTubeError(
            "YouTube credentials not configured. "
            "Set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in .env, "
            "then complete OAuth2 flow."
        )

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.http import MediaIoBaseUpload

        creds = Credentials.from_authorized_user_json(credentials_json) if credentials_json else None
        if creds is None:
            raise YouTubeError("No valid YouTube OAuth2 credentials provided.")

        service = _get_service(creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:500],
                "categoryId": "22",   # People & Blogs
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaIoBaseUpload(
            io.BytesIO(video_bytes),
            mimetype="video/mp4",
            chunksize=_CHUNK_SIZE,
            resumable=True,
        )

        loop = asyncio.get_event_loop()
        video_id = await loop.run_in_executor(
            None,
            partial(_execute_upload, service, body, media),
        )
        logger.info("YouTube upload complete: https://youtu.be/%s", video_id)
        return video_id

    except YouTubeError:
        raise
    except Exception as e:
        raise YouTubeError(f"YouTube upload failed: {e}") from e


def _execute_upload(service, body: dict, media) -> str:
    """Blocking: execute resumable upload with progress logging."""
    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("YouTube upload: %d%%", int(status.progress() * 100))
    return response["id"]


async def get_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
