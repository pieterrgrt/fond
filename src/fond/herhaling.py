"""Herhaling binnen de app: welke technieken zijn toe aan oefening?

Elke keer dat je een les kookt waarin een techniek voorkomt (aangeleerd of herhaald),
telt dat als oefening. Hoe vaker je hem hebt geoefend, hoe langer de pauze tot de
volgende keer: het principe van spaced repetition, zoals in Anki maar dan met je handen.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from fond.content.loader import Catalogus
from fond.content.models import Les, Techniek

# Pauze in dagen na de 1e, 2e, 3e... oefening.
INTERVALLEN = (3, 7, 14, 30, 60, 120)


@dataclass(frozen=True)
class Herhaling:
    techniek: Techniek
    keer_geoefend: int
    laatst: date
    toe_op: date
    # Lessen waarin je deze techniek kunt oefenen, de meest geschikte eerst.
    lessen: tuple[Les, ...]

    def dagen_over_tijd(self, vandaag: date) -> int:
        return (vandaag - self.toe_op).days


def volgende_datum(keer_geoefend: int, laatst: date) -> date:
    interval = INTERVALLEN[min(keer_geoefend, len(INTERVALLEN)) - 1]
    return laatst + timedelta(days=interval)


def lessen_met_techniek(cat: Catalogus, techniek_id: str) -> list[Les]:
    return [
        les
        for les in cat.alle_lessen()
        if techniek_id in les.meta.technieken or techniek_id in les.meta.herhaalt
    ]


def te_herhalen(
    cat: Catalogus,
    gekookt: Iterable[tuple[str, date]],
    vandaag: date,
    open_lessen: set[str] | None = None,
) -> list[Herhaling]:
    """Technieken die vandaag (of eerder) aan herhaling toe zijn.

    `gekookt` zijn (les_id, datum)-paren uit je reflecties. Meerdere oefeningen op
    dezelfde dag tellen als één. Lessen die open zijn maar nog niet gedaan, staan
    vooraan bij de suggesties: dan herhaal je én leer je iets nieuws.
    """
    oefendagen: dict[str, set[date]] = {}
    for les_id, dag in gekookt:
        les = cat.lessen.get(les_id)
        if les is None:
            continue
        for t in {*les.meta.technieken, *les.meta.herhaalt}:
            oefendagen.setdefault(t, set()).add(dag)

    gedaan = {les_id for les_id, _ in gekookt}
    resultaat = []
    for t_id, dagen in oefendagen.items():
        laatst = max(dagen)
        toe_op = volgende_datum(len(dagen), laatst)
        if toe_op > vandaag:
            continue
        kandidaten = lessen_met_techniek(cat, t_id)
        if open_lessen is not None:
            kandidaten = [les for les in kandidaten if les.id in open_lessen or les.id in gedaan]
        kandidaten.sort(key=lambda les: (les.id in gedaan,))
        resultaat.append(
            Herhaling(cat.technieken[t_id], len(dagen), laatst, toe_op, tuple(kandidaten))
        )
    resultaat.sort(key=lambda h: h.toe_op)
    return resultaat
