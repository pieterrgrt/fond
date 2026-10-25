"""De database: alleen wat jij doet (voortgang, reflecties, je boodschappenlijst).

De inhoud zelf staat in git. Lessen worden hier aangeduid met hun `id` uit de
frontmatter, niet met de bestandsnaam, zodat je bestanden kunt hernoemen.
"""

from collections.abc import Iterator
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Reflectie(Base):
    """'Proeven': wat je na het koken vastlegt. Een les is af als er één is."""

    __tablename__ = "reflectie"

    id: Mapped[int] = mapped_column(primary_key=True)
    les_id: Mapped[str] = mapped_column(String(100), index=True)
    gekookt_op: Mapped[date] = mapped_column(Date)
    porties: Mapped[int] = mapped_column(Integer, default=1)
    cijfer: Mapped[int] = mapped_column(Integer)  # 1–10
    wat_lukte: Mapped[str] = mapped_column(Text, default="")
    wat_niet: Mapped[str] = mapped_column(Text, default="")
    volgende_keer: Mapped[str] = mapped_column(Text, default="")
    foto: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aangemaakt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Vinkje(Base):
    """Een afgevinkt punt van de opdracht-checklist.

    `punt` is een korte hash van de tekst: pas je de tekst aan, dan begint dat punt
    opnieuw. Dat is bewust; het is dan een andere opdracht.
    """

    __tablename__ = "vinkje"

    les_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    punt: Mapped[str] = mapped_column(String(16), primary_key=True)
    aangevinkt: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BeheersteModule(Base):
    """Een module die je via de zelftoets hebt overgeslagen."""

    __tablename__ = "beheerste_module"

    module_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    op: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LijstItem(Base):
    """Een les (met aantal porties) op de huidige boodschappenlijst."""

    __tablename__ = "lijst_item"

    les_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    porties: Mapped[int] = mapped_column(Integer)
    toegevoegd: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


@event.listens_for(Engine, "connect")
def _sqlite_pragma(dbapi_connection, _record) -> None:
    # WAL: lezen en schrijven tegelijk; foreign keys staan in SQLite standaard uit.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def maak_engine(url: str) -> Engine:
    return create_engine(url, connect_args={"check_same_thread": False})


def maak_sessiefabriek(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def sessies(fabriek: sessionmaker[Session]) -> Iterator[Session]:
    with fabriek() as sessie:
        yield sessie
