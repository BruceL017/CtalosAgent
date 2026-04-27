from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://agent:agent_secret@localhost:5432/agent_db"
    redis_url: str = "redis://localhost:6379"
    api_server_url: str = "http://localhost:3001"
    host: str = "0.0.0.0"
    port: int = 8000
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    zhipu_api_key: str = ""
    moonshot_api_key: str = ""
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Pro/zai-org/GLM-4.7"
    siliconflow_embedding_api_key: str = ""
    siliconflow_embedding_model: str = "Qwen/Qwen3-VL-Embedding-8B"
    siliconflow_embedding_base_url: str = "https://api.siliconflow.cn/v1"
    log_level: str = "INFO"
    artifacts_dir: str = "/app/artifacts"
    jwt_secret: str = "change-this-to-a-random-string-at-least-32-chars"
    encryption_key: str = "change-this-to-another-random-string-32-chars"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
