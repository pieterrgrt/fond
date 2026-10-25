"""Database bijwerken naar het nieuwste schema (Alembic), vanuit de app zelf."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

MIGRATIES = Path(__file__).parent / "migrations"


def alembic_config(url: str, engine: Engine | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIES))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["engine"] = engine
    return config


def migreer(url: str, engine: Engine | None = None) -> None:
    command.upgrade(alembic_config(url, engine), "head")
