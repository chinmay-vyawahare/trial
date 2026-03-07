from dotenv import load_dotenv
import os
import psycopg2  # or use 'import psycopg' for psycopg3
from pydantic_settings import BaseSettings

# Load .env file
load_dotenv(".env")

print(os.getenv("PG_HOST"))


class Settings(BaseSettings):
    PG_HOST: str = os.getenv("PG_HOST")
    PG_PORT: int = int(os.getenv("PG_PORT", 5432))
    PG_DATABASE: str = os.getenv("PG_DATABASE")
    PG_USER: str = os.getenv("PG_USER")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD")
    APP_NAME: str = os.getenv("APP_NAME", "Nokia Gantt Chart API")
    DEBUG: bool = bool(int(os.getenv("DEBUG", 1)))

    # Schema names within PG_DATABASE (hardcoded)
    UTILITY_SCHEMA: str = "pwc_agent_utility_schema"
    STAGING_SCHEMA: str = "pwc_macro_staging_schema"


settings = Settings()

# Connect using psycopg2 without using DATABASE_URL
try:
    connection = psycopg2.connect(
        host=settings.PG_HOST,
        port=settings.PG_PORT,
        database=settings.PG_DATABASE,
        user=settings.PG_USER,
        password=settings.PG_PASSWORD
    )
    print("Connection successful!")
except Exception as e:
    print(f"Connection failed: {e}")
