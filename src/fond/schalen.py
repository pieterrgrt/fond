"""Porties schalen en hoeveelheden netjes weergeven.

Niet alles schaalt lineair. Voor drie keer zoveel chili heb je geen drie keer zoveel
olie in de pan nodig, en specerijen worden snel te veel. Daarom heeft elk
ingrediënt een schaalregel (zie `Schaal`), en wordt het resultaat afgerond op
hoeveelheden die je in een keuken echt afmeet.
"""

import math
from dataclasses import dataclass

from fond.content.models import Eenheid, Ingredient, Recept, ReceptIngredient, Schaal

# Eenheden die we bij elkaar optellen: kg wordt g, l wordt ml.
BASIS = {Eenheid.kg: (Eenheid.g, 1000), Eenheid.l: (Eenheid.ml, 1000)}


def factor_voor(schaal: Schaal, factor: float) -> float:
    """De werkelijke vermenigvuldiging voor een schaalregel.

    'beperkt' gaat de helft van de weg: ×3 porties wordt ×2, ×2 wordt ×1,5,
    en halveren wordt ×0,75.
    """
    if schaal is Schaal.vast:
        return 1.0
    if schaal is Schaal.beperkt:
        return 1 + (factor - 1) / 2
    return factor


def naar_basis(hoeveelheid: float, eenheid: Eenheid) -> tuple[float, Eenheid]:
    if eenheid in BASIS:
        basis, keer = BASIS[eenheid]
        return hoeveelheid * keer, basis
    return hoeveelheid, eenheid


def rond_af(hoeveelheid: float, eenheid: Eenheid, heel: bool = False) -> float:
    """Rond af op een hoeveelheid die je echt afmeet."""
    if hoeveelheid <= 0:
        return 0
    hoeveelheid, eenheid = naar_basis(hoeveelheid, eenheid)
    if eenheid in (Eenheid.g, Eenheid.ml):
        if hoeveelheid < 20:
            stap = 1
        elif hoeveelheid < 100:
            stap = 5
        elif hoeveelheid < 1000:
            stap = 10
        else:
            stap = 50
        return max(stap, round(hoeveelheid / stap) * stap)
    if eenheid in (Eenheid.el, Eenheid.tl):
        stap = 0.25 if hoeveelheid < 1 else 0.5
        return max(0.25, round(hoeveelheid / stap) * stap)
    if heel:
        # Kleine marge, zodat 2,0000001 niet naar 3 gaat.
        return max(1, math.ceil(hoeveelheid - 0.05))
    return max(0.5, round(hoeveelheid * 2) / 2)


_BREUKEN = {0.25: "¼", 0.5: "½", 0.75: "¾"}


def getal(waarde: float) -> str:
    """1.5 -> '1½', 0.25 -> '¼', 2.0 -> '2', 1.2 -> '1,2'."""
    geheel, rest = int(waarde), round(waarde - int(waarde), 2)
    if rest == 0:
        return str(geheel)
    if rest in _BREUKEN:
        return (str(geheel) if geheel else "") + _BREUKEN[rest]
    return f"{waarde:.1f}".replace(".", ",")


_MEERVOUD = {
    Eenheid.teen: "tenen",
    Eenheid.blik: "blikken",
    Eenheid.pot: "potten",
    Eenheid.takje: "takjes",
    Eenheid.plak: "plakken",
    Eenheid.bos: "bossen",
}


def toon(hoeveelheid: float | None, eenheid: Eenheid | None) -> str:
    """Leesbare hoeveelheid: '250 g', '1,2 kg', '1½ el', '2 tenen', '1 stuk'."""
    if hoeveelheid is None or eenheid is None:
        return "naar smaak"
    hoeveelheid, eenheid = naar_basis(hoeveelheid, eenheid)
    if eenheid in (Eenheid.g, Eenheid.ml) and hoeveelheid >= 1000:
        groot = "kg" if eenheid is Eenheid.g else "l"
        return f"{getal(round(hoeveelheid / 1000, 2))} {groot}"
    if eenheid in (Eenheid.g, Eenheid.ml):
        return f"{getal(hoeveelheid)} {eenheid.value}"
    if eenheid is Eenheid.stuk:
        return getal(hoeveelheid)
    naam = _MEERVOUD.get(eenheid, eenheid.value) if hoeveelheid > 1 else eenheid.value
    return f"{getal(hoeveelheid)} {naam}"


@dataclass(frozen=True)
class GeschaaldIngredient:
    bron: ReceptIngredient
    ingredient: Ingredient
    hoeveelheid: float | None  # afgerond
    eenheid: Eenheid | None
    exact: float | None  # niet afgerond; nodig om lijsten op te tellen

    @property
    def tekst(self) -> str:
        return toon(self.hoeveelheid, self.eenheid)


def schaal_ingredient(
    ri: ReceptIngredient, ingredient: Ingredient, factor: float
) -> GeschaaldIngredient:
    if ri.hoeveelheid is None or ri.eenheid is None:
        return GeschaaldIngredient(ri, ingredient, None, None, None)
    exact = ri.hoeveelheid * factor_voor(ri.schaal, factor)
    exact, eenheid = naar_basis(exact, ri.eenheid)
    return GeschaaldIngredient(
        ri, ingredient, rond_af(exact, eenheid, ingredient.heel), eenheid, exact
    )


def schaal_recept(
    recept: Recept, ingredienten: dict[str, Ingredient], porties: int
) -> list[GeschaaldIngredient]:
    factor = porties / recept.porties
    return [schaal_ingredient(ri, ingredienten[ri.item], factor) for ri in recept.ingredienten]
