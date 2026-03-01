from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    PG_HOST: str
    PG_PORT: int = 5432
    PG_DATABASE: str
    PG_USER: str
    PG_PASSWORD: str
    APP_NAME: str = "Nokia Gantt Chart API"
    DEBUG: bool = True

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"


settings = Settings()
