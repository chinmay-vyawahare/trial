from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# URL-encode password
password_encoded = quote_plus(settings.PG_PASSWORD)

# Single engine — both schemas live in the same database (PG_DATABASE)
engine = create_engine(
    f"postgresql+psycopg2://{settings.PG_USER}:{password_encoded}"
    f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DATABASE}",
    pool_pre_ping=True,
)

# Both point to the same engine now (single database, different schemas)
config_engine = engine

# Fully-qualified staging table name for raw SQL queries
STAGING_TABLE = f"{settings.STAGING_SCHEMA}.stg_ndpd_mbt_tmobile_macro_combined"

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ConfigSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base for staging/read tables (pwc_macro_staging_schema)."""
    pass


class ConfigBase(DeclarativeBase):
    """Base for config/utility tables (pwc_agent_utility_schema)."""
    pass


def get_db():
    """Session for staging data queries."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_config_db():
    """Session for config/utility tables."""
    db = ConfigSessionLocal()
    try:
        yield db
    finally:
        db.close()
