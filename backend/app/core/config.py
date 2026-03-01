from pydantic_settings import BaseSettings
import dotenv
dotenv.load_dotenv()
import os

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    APP_NAME: str = "Nokia Gantt Chart API"
    DEBUG: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
