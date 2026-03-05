from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# URL-encode password
password_encoded = quote_plus(settings.PG_PASSWORD)

# Engine for nokia_bkg_sample (staging data — read-only queries)
engine = create_engine(
    f"postgresql+psycopg2://{settings.PG_USER}:{password_encoded}"
    f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DATABASE}",
    pool_pre_ping=True,
)

# Engine for schedular_agent (config tables — milestone definitions, user filters, etc.)
config_engine = create_engine(
    f"postgresql+psycopg2://{settings.PG_USER}:{password_encoded}"
    f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.CONFIG_PG_DATABASE}",
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ConfigSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=config_engine)


class Base(DeclarativeBase):
    """Base for staging/read tables (nokia_bkg_sample)."""
    pass


class ConfigBase(DeclarativeBase):
    """Base for config tables (schedular_agent DB)."""
    pass


def get_db():
    """Session for nokia_bkg_sample (staging data)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_config_db():
    """Session for schedular_agent (config tables)."""
    db = ConfigSessionLocal()
    try:
        yield db
    finally:
        db.close()
