"""Het inhoudsformaat van Fond.

Alle lessen, recepten en ingrediënten staan als YAML/Markdown in `content/`.
Deze Pydantic-modellen beschrijven hoe die bestanden eruit moeten zien. Bij het
opstarten (en met `uv run fond check`) wordt alles hiertegen gevalideerd, zodat een
tikfout in een les een duidelijke foutmelding geeft in plaats van een kapotte pagina.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Strikt(BaseModel):
    # Onbekende velden zijn een fout: zo vang je tikfouten als `hoeveelheit` op.
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Winkel en ingrediënten -------------------------------------------------------


class Afdeling(Strikt):
    id: str = Field(pattern=SLUG)
    naam: str
    naam_de: str


class Eenheid(StrEnum):
    g = "g"
    kg = "kg"
    ml = "ml"
    l = "l"  # noqa: E741 (liter)
    el = "el"  # eetlepel, 15 ml
    tl = "tl"  # theelepel, 5 ml
    stuk = "stuk"
    teen = "teen"
    blik = "blik"
    pot = "pot"
    bos = "bos"
    takje = "takje"
    plak = "plak"
    snuf = "snuf"
    handvol = "handvol"


class Verpakking(Strikt):
    hoeveelheid: float = Field(gt=0)
    eenheid: Eenheid
    # Indicatieve prijs in euro bij de Aldi Süd. Prijzen wisselen: het is een schatting.
    prijs: float | None = Field(default=None, ge=0)
    # Hoe het in de winkel ligt, bv. "net van 3 bollen". Zonder: "500 g".
    omschrijving: str | None = None


class Ingredient(Strikt):
    id: str = Field(pattern=SLUG)
    naam: str
    naam_de: str
    afdeling: str
    verpakking: Verpakking | None = None
    # Basisvoorraad (zout, olie, specerijen): staat op de lijst onder "check thuis".
    voorraad: bool = False
    # Altijd in hele stuks (eieren, uien): bij schalen naar boven afronden.
    heel: bool = False


class Techniek(Strikt):
    id: str = Field(pattern=SLUG)
    naam: str
    # Franse term, als die bestaat (bv. "brunoise").
    frans: str | None = None
    uitleg: str


# --- Cursusstructuur --------------------------------------------------------------


class Module(Strikt):
    id: str = Field(pattern=SLUG)
    titel: str
    uitleg: str
    # Modules die eerst af (of beheerst) moeten zijn.
    vereist: list[str] = []
    # Uitspraken waarmee je zelf aangeeft dat je de module al beheerst en mag overslaan.
    zelftoets: list[str] = []


class Niveau(Strikt):
    id: str = Field(pattern=SLUG)
    naam: str
    ondertitel: str
    uitleg: str
    modules: list[Module]


class Cursus(Strikt):
    niveaus: list[Niveau]


# --- Lessen en recepten -----------------------------------------------------------


class Schaal(StrEnum):
    lineair = "lineair"  # ×3 porties is ×3 de hoeveelheid
    beperkt = "beperkt"  # ×3 porties is ×2: olie, zout, specerijen
    vast = "vast"  # schaalt niet mee: een laurierblad, olie om de pan in te vetten


_DUUR = re.compile(r"^(?:(\d+)u)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_duur(tekst: str) -> int:
    """'1u30m' -> 5400, '45s' -> 45, '10m' -> 600."""
    match = _DUUR.match(tekst.strip())
    if not match or not any(match.groups()):
        raise ValueError(f"onbekende duur {tekst!r}; gebruik bv. '10m', '1u30m' of '45s'")
    uren, minuten, seconden = (int(g) if g else 0 for g in match.groups())
    return uren * 3600 + minuten * 60 + seconden


class ReceptIngredient(Strikt):
    item: str
    # Leeg betekent "naar smaak".
    hoeveelheid: float | None = Field(default=None, gt=0)
    eenheid: Eenheid | None = None
    schaal: Schaal = Schaal.lineair
    notitie: str | None = None
    # Optionele kop waaronder het ingrediënt staat, bv. "Voor de dressing".
    groep: str | None = None


class Stap(Strikt):
    tekst: str
    # Timer als tekst ('8m', '1u15m'); in seconden beschikbaar via `timer_seconden`.
    timer: str | None = None
    timer_label: str | None = None

    @field_validator("timer")
    @classmethod
    def _timer_geldig(cls, waarde: str | None) -> str | None:
        if waarde is not None:
            parse_duur(waarde)
        return waarde

    @property
    def timer_seconden(self) -> int | None:
        return parse_duur(self.timer) if self.timer else None


class MealPrep(Strikt):
    koelkast_dagen: int = Field(ge=0, le=7)
    # Hoeveel maanden het in de vriezer kan; 0 = niet invriezen.
    vriezer_maanden: int = Field(default=0, ge=0, le=6)
    opwarmen: str
    variatie: str | None = None
    tip: str | None = None


class Recept(Strikt):
    naam: str
    porties: int = Field(ge=1)
    tijd_actief: int = Field(ge=0, description="minuten aan het werk")
    tijd_totaal: int = Field(ge=0, description="minuten inclusief wachten")
    eiwit_per_portie: int | None = Field(default=None, ge=0, description="grove schatting, gram")
    ingredienten: list[ReceptIngredient]
    stappen: list[Stap]
    meal_prep: MealPrep | None = None
    # Een glas en een stuk kaas dat erbij past: om te leren, niet verplicht.
    wijn: str | None = None


class Kaart(Strikt):
    voor: str
    achter: str
    tags: list[str] = []


class LesMeta(Strikt):
    """De frontmatter van een lesbestand."""

    id: str = Field(pattern=SLUG)
    titel: str
    module: str
    volgorde: int = Field(ge=1)
    duur: int = Field(ge=0, description="minuten voor de hele les, koken inbegrepen")
    samenvatting: str
    vereist: list[str] = []
    technieken: list[str] = []
    herhaalt: list[str] = []
    recept: Recept | None = None
    opdracht: list[str] = Field(min_length=1)
    kaarten: list[Kaart] = []


class Sectie(BaseModel):
    titel: str
    html: str


class Les(BaseModel):
    model_config = ConfigDict(frozen=True)

    meta: LesMeta
    bestand: str
    secties: list[Sectie]

    @property
    def id(self) -> str:
        return self.meta.id

    def sectie(self, titel: str) -> Sectie | None:
        return next((s for s in self.secties if s.titel.lower() == titel.lower()), None)
