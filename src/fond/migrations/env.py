"""Alembic-omgeving. Migraties draaien automatisch bij het opstarten van de app."""

from alembic import context

from fond.db import Base, maak_engine

config = context.config
engine = config.attributes.get("engine") or maak_engine(config.get_main_option("sqlalchemy.url"))

with engine.connect() as verbinding:
    context.configure(
        connection=verbinding,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite kan kolommen niet wijzigen; batch-modus omzeilt dat
    )
    with context.begin_transaction():
        context.run_migrations()
