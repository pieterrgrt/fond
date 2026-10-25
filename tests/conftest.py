"""Gedeelde testopzet: een kleine nep-cursus in een tijdelijke map."""

import textwrap
from pathlib import Path

import pytest

from fond.content.loader import laad_catalogus

WINKEL = """
afdelingen:
  - {id: groente, naam: Groente, naam_de: Gemüse}
  - {id: droog, naam: Droog, naam_de: Trocken}
  - {id: kruiden, naam: Kruiden, naam_de: Gewürze}
"""

INGREDIENTEN = """
ui: {naam: Ui, naam_de: Zwiebeln, afdeling: groente, heel: true,
     verpakking: {hoeveelheid: 8, eenheid: stuk, prijs: 1.20}}
rijst: {naam: Rijst, naam_de: Reis, afdeling: droog,
        verpakking: {hoeveelheid: 1, eenheid: kg, prijs: 2.00}}
olie: {naam: Olie, naam_de: Öl, afdeling: kruiden, voorraad: true}
zout: {naam: Zout, naam_de: Salz, afdeling: kruiden, voorraad: true}
"""

TECHNIEKEN = """
snijden: {naam: Snijden, uitleg: Met een mes.}
koken: {naam: Koken, uitleg: In water.}
bakken: {naam: Bakken, uitleg: In vet.}
"""

CURSUS = """
niveaus:
  - id: een
    naam: Een
    ondertitel: Eerste
    uitleg: Het eerste niveau.
    modules:
      - {id: basis, titel: Basis, uitleg: De basis., zelftoets: [Ik kan het.]}
      - {id: vervolg, titel: Vervolg, uitleg: Daarna., vereist: [basis]}
      - {id: leeg, titel: Leeg, uitleg: Nog geen lessen.}
"""


def les(id_, module, volgorde, *, vereist=(), technieken=(), herhaalt=(), recept=True):
    recept_yaml = (
        textwrap.dedent("""
        recept:
          naam: Rijst met ui
          porties: 2
          tijd_actief: 10
          tijd_totaal: 20
          ingredienten:
            - {item: rijst, hoeveelheid: 200, eenheid: g}
            - {item: ui, hoeveelheid: 1, eenheid: stuk}
            - {item: olie, hoeveelheid: 1, eenheid: el, schaal: beperkt}
            - {item: zout}
          stappen:
            - {tekst: Koken., timer: 12m}
    """)
        if recept
        else ""
    )
    return (
        f"---\nid: {id_}\ntitel: Les {id_}\nmodule: {module}\nvolgorde: {volgorde}\n"
        f"duur: 30\nsamenvatting: Over {id_}.\nvereist: {list(vereist)}\n"
        f"technieken: {list(technieken)}\nherhaalt: {list(herhaalt)}\n"
        f"{recept_yaml}opdracht: [Gedaan.]\n---\n\n## Theorie\n\nTekst over [[snijden]].\n\n"
        "## Techniek\n\nOefenen.\n"
    )


def schrijf_inhoud(map_: Path, lessen: dict[str, str] | None = None) -> Path:
    (map_ / "een").mkdir(parents=True, exist_ok=True)
    (map_ / "winkel.yaml").write_text(WINKEL)
    (map_ / "ingredienten.yaml").write_text(INGREDIENTEN)
    (map_ / "technieken.yaml").write_text(TECHNIEKEN)
    (map_ / "cursus.yaml").write_text(CURSUS)
    if lessen is None:
        lessen = {
            "01-a.md": les("a", "basis", 1, technieken=["snijden"]),
            "02-b.md": les(
                "b", "basis", 2, vereist=["a"], technieken=["koken"], herhaalt=["snijden"]
            ),
            "03-c.md": les("c", "vervolg", 1, technieken=["bakken"], herhaalt=["koken"]),
        }
    for naam, tekst in lessen.items():
        (map_ / "een" / naam).write_text(tekst)
    return map_


@pytest.fixture
def inhoud(tmp_path: Path) -> Path:
    return schrijf_inhoud(tmp_path / "content")


@pytest.fixture
def cat(inhoud: Path):
    return laad_catalogus(inhoud)
