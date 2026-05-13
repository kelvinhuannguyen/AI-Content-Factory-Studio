from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://aicfs:password@localhost:5432/aicfs"
    # Neon pooled URL (dùng PgBouncer, cho Alembic migrations)
    # Nếu không set, fallback về database_url
    database_url_pooled: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # KymaAPI
    kymaapi_key: str = ""
    kymaapi_base_url: str = "https://api.kymaapi.com/v1"
    kymaapi_llm_model: str = "gemini-2.5-flash"
    kymaapi_llm_model_long: str = "deepseek-v3"
    # Vision models for quality scoring (GPT-4o deprecated → GPT-5.x)
    kymaapi_vision_model: str = "gpt-5.4"          # primary — fast + multimodal
    kymaapi_vision_model_fallback: str = "gpt-5.5"  # fallback — latest, expensive
    kymaapi_video_model: str = "kling-3-pro"
    kymaapi_image_model: str = "flux-1.1-ultra"
    kymaapi_tts_model: str = "eleven-multilingual-v2"
    kymaapi_tts_voice_id: str = "21m00Tcm4TlvDq8ikWAM"   # Rachel — ElevenLabs
    kymaapi_music_model: str = "minimax-music-pro"

    # Image generation
    comfyui_url: str = "http://127.0.0.1:8188"
    runpod_comfyui_url: str = ""
    chatfpt_image_api_key: str = ""
    banana_api_key: str = ""

    # Audio
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""

    # Music
    suno_api_key: str = ""
    suno_api_base_url: str = "https://api.sunoapi.com/api/v1"

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "aicfs-media"
    r2_public_url: str = ""

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_api_key: str = ""

    # Notifications — Gmail
    # Option A (personal Gmail): set GMAIL_APP_PASSWORD (create at myaccount.google.com/apppasswords)
    gmail_sender_email: str = "kelvinhuannguyen@gmail.com"
    gmail_app_password: str = ""   # 16-char app password from Google Account settings
    # Option B (Google Workspace + DWD): path to service account JSON file
    gmail_service_account_json: str = "credentials/gmail_service_account.json"
    notification_email: str = "kelvinhuannguyen@gmail.com"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # App
    app_secret_key: str = "change-me"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
