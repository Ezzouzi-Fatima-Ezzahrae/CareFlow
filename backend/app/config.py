import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env BEFORE pydantic-settings reads the environment.
# override=True makes .env values win over any pre-existing OS env vars,
# which is what we want on Windows where users often have leftover global keys.
_DOTENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_DOTENV_PATH, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Provider switch: 'gemini' (free) or 'openai' (paid)
    llm_provider: str = "gemini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_vision_model: str = "gemini-1.5-flash"

    # OpenAI
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    vision_model: str = "gpt-4o"

    database_url: str = "sqlite:///./careflow.db"
    storage_dir: str = "./storage"
    max_upload_mb: int = 10


settings = Settings()
