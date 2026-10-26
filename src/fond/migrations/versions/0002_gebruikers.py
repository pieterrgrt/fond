"""gebruikers: meerdere accounts, elk met eigen voortgang

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 20:30:00

Elke tabel krijgt een kolom gebruiker_id. Bestaande gegevens (van de tijd dat Fond
één gebruiker had) gaan naar account 1, met inlognaam "eigenaar". Bij het opstarten
krijgt dat account het oude wachtwoord uit FOND_PASSWORD_HASH (zie
gebruikers.koppel_eigenaar). SQLite kan geen primaire sleutel wijzigen, dus de
tabellen worden opnieuw opgebouwd.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NU = sa.text("(CURRENT_TIMESTAMP)")


def gebruiker_id(tabel: str, primary_key: bool) -> sa.Column:
    return sa.Column(
        "gebruiker_id",
        sa.Integer(),
        sa.ForeignKey("gebruiker.id", name=f"fk_{tabel}_gebruiker", ondelete="CASCADE"),
        primary_key=primary_key,
        nullable=False,
    )


# Per tabel: de nieuwe kolommen (zonder gebruiker_id), en de primaire sleutel.
TABELLEN = {
    "reflectie": (
        [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("les_id", sa.String(100), nullable=False),
            sa.Column("gekookt_op", sa.Date(), nullable=False),
            sa.Column("porties", sa.Integer(), nullable=False),
            sa.Column("cijfer", sa.Integer(), nullable=False),
            sa.Column("wat_lukte", sa.Text(), nullable=False),
            sa.Column("wat_niet", sa.Text(), nullable=False),
            sa.Column("volgende_keer", sa.Text(), nullable=False),
            sa.Column("foto", sa.String(100), nullable=True),
            sa.Column("aangemaakt", sa.DateTime(), server_default=NU, nullable=False),
        ],
        False,
    ),
    "vinkje": (
        [
            sa.Column("les_id", sa.String(100), primary_key=True),
            sa.Column("punt", sa.String(16), primary_key=True),
            sa.Column("aangevinkt", sa.DateTime(), server_default=NU, nullable=False),
        ],
        True,
    ),
    "beheerste_module": (
        [
            sa.Column("module_id", sa.String(100), primary_key=True),
            sa.Column("op", sa.DateTime(), server_default=NU, nullable=False),
        ],
        True,
    ),
    "lijst_item": (
        [
            sa.Column("les_id", sa.String(100), primary_key=True),
            sa.Column("porties", sa.Integer(), nullable=False),
            sa.Column("toegevoegd", sa.DateTime(), server_default=NU, nullable=False),
        ],
        True,
    ),
}


def upgrade() -> None:
    op.create_table(
        "gebruiker",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("naam", sa.String(100), nullable=False),
        sa.Column("wachtwoord_hash", sa.String(200), nullable=False),
        sa.Column("sessie_versie", sa.Integer(), nullable=False),
        sa.Column("widget_sleutel", sa.String(64), nullable=True, unique=True),
        sa.Column("aangemaakt", sa.DateTime(), server_default=NU, nullable=False),
        sqlite_autoincrement=True,  # id's nooit hergebruiken (zie db.Gebruiker)
    )
    verbinding = op.get_bind()
    if any(verbinding.execute(sa.text(f"SELECT 1 FROM {t} LIMIT 1")).first() for t in TABELLEN):
        verbinding.execute(
            sa.text(
                "INSERT INTO gebruiker (id, email, naam, wachtwoord_hash, sessie_versie) "
                "VALUES (1, 'eigenaar', 'Eigenaar', '', 1)"
            )
        )

    op.drop_index("ix_reflectie_les_id", table_name="reflectie")
    for tabel, (kolommen, in_sleutel) in TABELLEN.items():
        op.rename_table(tabel, f"{tabel}_oud")
        op.create_table(tabel, gebruiker_id(tabel, in_sleutel), *kolommen)
        namen = ", ".join(k.name for k in kolommen)
        verbinding.execute(
            sa.text(f"INSERT INTO {tabel} (gebruiker_id, {namen}) SELECT 1, {namen} FROM {tabel}_oud")
        )
        op.drop_table(f"{tabel}_oud")
        op.create_index(f"ix_{tabel}_gebruiker_id", tabel, ["gebruiker_id"])
    op.create_index("ix_reflectie_les_id", "reflectie", ["les_id"])


def downgrade() -> None:
    raise NotImplementedError("Terug naar één gebruiker kan niet zonder gegevens te verliezen.")
