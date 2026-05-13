import logging
from fastapi import APIRouter, HTTPException
import httpx

from ...config import get_settings
from ...services.llm_service import chat_json, LLMError
from ...utils.prompt_templates import TOPIC_TRENDING_SYSTEM, topic_trending_user

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def _fetch_youtube_trending(genre: str, language: str = "vi") -> list[str]:
    """Fetch trending video titles from YouTube Data API."""
    if not settings.youtube_api_key:
        logger.warning("YOUTUBE_API_KEY not set — using fallback mock titles")
        return _mock_titles(genre)

    lang_map = {"vi": "vi", "en": "en"}
    hl = lang_map.get(language, "vi")

    params = {
        "part":           "snippet",
        "type":           "video",
        "order":          "viewCount",
        "publishedAfter": _days_ago(7),
        "maxResults":     25,
        "relevanceLanguage": hl,
        "q":              genre,
        "key":            settings.youtube_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(YOUTUBE_SEARCH_URL, params=params)
        if resp.status_code != 200:
            logger.warning("YouTube API error %s — using mock", resp.status_code)
            return _mock_titles(genre)
        items = resp.json().get("items", [])
        return [item["snippet"]["title"] for item in items if item.get("snippet")]
    except Exception as e:
        logger.warning("YouTube fetch failed: %s — using mock", e)
        return _mock_titles(genre)


def _days_ago(n: int) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(days=n)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _mock_titles(genre: str) -> list[str]:
    """Fallback mock titles when YouTube API key is not configured."""
    return [
        f"Top 10 {genre} tips that changed my life",
        f"I tried {genre} for 30 days — shocking results",
        f"Why everyone is wrong about {genre}",
        f"The {genre} secret no one talks about",
        f"{genre} in 2025: what you need to know",
        f"How I mastered {genre} in 30 days",
        f"Stop making these {genre} mistakes",
        f"The complete {genre} guide for beginners",
        f"{genre} hacks that actually work",
        f"My honest {genre} review after 1 year",
    ]


@router.post("/trending")
async def get_trending_topics(body: dict):
    """
    Scrape YouTube trending → GPT-4o analysis → 10 topic suggestions.
    Body: { genre, style, production_type, language? }
    """
    genre           = body.get("genre", "education")
    style           = body.get("style", "educational")
    production_type = body.get("production_type", "short_video")
    language        = body.get("language", "vi")

    # 1. Fetch YouTube trending titles
    raw_titles = await _fetch_youtube_trending(genre, language)

    # 2. GPT-4o analysis
    try:
        user_prompt = topic_trending_user(raw_titles, genre, style, production_type, language)
        result = await chat_json(TOPIC_TRENDING_SYSTEM, user_prompt, temperature=0.8)
        # Result may be wrapped in a key or be a direct list
        topics = result if isinstance(result, list) else result.get("topics", result.get("data", []))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

    return {
        "topics": topics[:10],
        "source_titles_count": len(raw_titles),
        "genre": genre,
        "language": language,
    }
