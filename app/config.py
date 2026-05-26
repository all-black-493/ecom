from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_secret: str = "dev-secret"
    app_port: int = 8000

    database_url: str = "postgresql+psycopg2://lumen:lumen@localhost:5432/lumen"

    cubejs_api_url: str = "http://localhost:4000/cubejs-api/v1"
    cube_api_secret: str = "cube-secret-change-me"

    gcp_project_id: str = ""
    bq_dataset_raw: str = "lumen_raw"
    bq_dataset_mart: str = "lumen_mart"


@lru_cache
def get_settings() -> Settings:
    return Settings()
