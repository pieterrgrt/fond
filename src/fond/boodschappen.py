"""Boodschappenlijsten: recepten samenvoegen en sorteren op de looproute.

Gelijke ingrediënten uit verschillende lessen worden opgeteld (in dezelfde eenheid),
pas daarna afgerond, en omgerekend naar verpakkingen zoals je ze in de Aldi koopt.
Basisvoorraad (zout, olie, specerijen) komt apart onder 'check thuis'.
"""

import math
from dataclasses import dataclass, field

from fond.content.loader import Catalogus
from fond.content.models import Afdeling, Eenheid, Ingredient, Les
from fond.schalen import naar_basis, rond_af, schaal_ingredient, toon

CHECK_THUIS = Afdeling(id="check-thuis", naam="Check thuis", naam_de="Vorrat")


@dataclass
class Regel:
    ingredient: Ingredient
    eenheid: Eenheid | None
    exact: float | None = None
    lessen: list[str] = field(default_factory=list)

    @property
    def hoeveelheid(self) -> float | None:
        if self.exact is None or self.eenheid is None:
            return None
        return rond_af(self.exact, self.eenheid, self.ingredient.heel)

    @property
    def tekst(self) -> str:
        return toon(self.hoeveelheid, self.eenheid)

    @property
    def verpakkingen(self) -> int | None:
        """Hoeveel verpakkingen je moet kopen, als de eenheid overeenkomt."""
        verpakking = self.ingredient.verpakking
        if verpakking is None or self.exact is None or self.eenheid is None:
            return None
        inhoud, eenheid = naar_basis(verpakking.hoeveelheid, verpakking.eenheid)
        if eenheid != self.eenheid:
            return None
        # Kleine marge: 501 g mag nog in één pak van 500 g.
        return max(1, math.ceil(self.exact / inhoud - 0.02))

    @property
    def verpakking_tekst(self) -> str | None:
        aantal, verpakking = self.verpakkingen, self.ingredient.verpakking
        if aantal is None or verpakking is None:
            return None
        if (
            verpakking.eenheid in (Eenheid.blik, Eenheid.pot, Eenheid.bos)
            and verpakking.hoeveelheid == 1
        ):
            return None  # "2 blikken" is al duidelijk
        if verpakking.omschrijving:
            return f"{aantal}× {verpakking.omschrijving}"
        return f"{aantal}× {toon(verpakking.hoeveelheid, verpakking.eenheid)}"

    @property
    def prijs(self) -> float | None:
        verpakking = self.ingredient.verpakking
        if self.verpakkingen is None or verpakking is None or verpakking.prijs is None:
            return None
        return round(self.verpakkingen * verpakking.prijs, 2)


@dataclass
class Groep:
    afdeling: Afdeling
    regels: list[Regel]


@dataclass
class Lijst:
    groepen: list[Groep]
    lessen: list[tuple[Les, int]]

    @property
    def schatting(self) -> float:
        """Geschatte prijs van alles behalve de basisvoorraad."""
        return round(
            sum(
                r.prijs or 0
                for g in self.groepen
                if g.afdeling.id != CHECK_THUIS.id
                for r in g.regels
            ),
            2,
        )

    @property
    def leeg(self) -> bool:
        return not self.groepen


def maak_lijst(cat: Catalogus, keuze: list[tuple[Les, int]]) -> Lijst:
    """Maak een lijst van (les, porties)-paren."""
    regels: dict[tuple[str, Eenheid | None], Regel] = {}
    for les, porties in keuze:
        recept = les.meta.recept
        if recept is None:
            continue
        factor = porties / recept.porties
        for ri in recept.ingredienten:
            ingredient = cat.ingredienten[ri.item]
            geschaald = schaal_ingredient(ri, ingredient, factor)
            sleutel = (ingredient.id, geschaald.eenheid)
            regel = regels.setdefault(sleutel, Regel(ingredient, geschaald.eenheid))
            if geschaald.exact is not None:
                regel.exact = (regel.exact or 0) + geschaald.exact
            if les.meta.titel not in regel.lessen:
                regel.lessen.append(les.meta.titel)

    # Hetzelfde ingrediënt zowel 'naar smaak' als met hoeveelheid: één regel is genoeg.
    met_hoeveelheid = {i for (i, e) in regels if e is not None}
    regels = {k: r for k, r in regels.items() if k[1] is not None or k[0] not in met_hoeveelheid}

    volgorde = {a.id: n for n, a in enumerate(cat.afdelingen)}
    per_afdeling: dict[str, list[Regel]] = {}
    for regel in regels.values():
        afdeling = CHECK_THUIS.id if regel.ingredient.voorraad else regel.ingredient.afdeling
        per_afdeling.setdefault(afdeling, []).append(regel)

    afdelingen = {a.id: a for a in cat.afdelingen} | {CHECK_THUIS.id: CHECK_THUIS}
    groepen = [
        Groep(afdelingen[a], sorted(r, key=lambda x: x.ingredient.naam.lower()))
        for a, r in sorted(per_afdeling.items(), key=lambda kv: volgorde.get(kv[0], 999))
    ]
    return Lijst(groepen=groepen, lessen=keuze)
