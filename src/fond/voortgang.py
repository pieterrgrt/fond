"""Ontgrendelen van modules en lessen.

Pure logica: krijgt de catalogus en wat je hebt gedaan, en zegt wat open is.
Geen database hier, zodat het makkelijk te testen is.

Regels:
- Een module is *voldaan* als al haar lessen af zijn, of als je haar via de
  zelftoets als beheerst hebt gemarkeerd.
- Een module gaat open als alle modules in haar `vereist` voldaan zijn.
- Een les gaat open als haar module open is en de lessen in haar `vereist`
  af zijn (of in een beheerste module zitten).
- Een les is af zodra je erover hebt gereflecteerd.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from fond.content.loader import Catalogus
from fond.content.models import Les, Module


class Status(StrEnum):
    op_slot = "op_slot"
    open = "open"
    bezig = "bezig"  # module: minstens één les af
    af = "af"
    beheerst = "beheerst"  # module: via zelftoets overgeslagen
    binnenkort = "binnenkort"  # module zonder lessen (nog niet geschreven)


@dataclass(frozen=True)
class Voortgang:
    afgeronde_lessen: frozenset[str] = field(default_factory=frozenset)
    beheerste_modules: frozenset[str] = field(default_factory=frozenset)


def module_voldaan(cat: Catalogus, vg: Voortgang, module_id: str) -> bool:
    if module_id in vg.beheerste_modules:
        return True
    lessen = cat.lessen_per_module.get(module_id, [])
    return bool(lessen) and all(les.id in vg.afgeronde_lessen for les in lessen)


def module_open(cat: Catalogus, vg: Voortgang, module: Module) -> bool:
    return all(module_voldaan(cat, vg, vereist) for vereist in module.vereist)


def module_status(cat: Catalogus, vg: Voortgang, module: Module) -> Status:
    lessen = cat.lessen_per_module.get(module.id, [])
    if module.id in vg.beheerste_modules:
        return Status.beheerst
    if not lessen:
        return Status.binnenkort
    if not module_open(cat, vg, module):
        return Status.op_slot
    klaar = sum(les.id in vg.afgeronde_lessen for les in lessen)
    if klaar == len(lessen):
        return Status.af
    return Status.bezig if klaar else Status.open


def _les_voldaan(cat: Catalogus, vg: Voortgang, les_id: str) -> bool:
    return les_id in vg.afgeronde_lessen or cat.lessen[les_id].meta.module in vg.beheerste_modules


def les_status(cat: Catalogus, vg: Voortgang, les: Les) -> Status:
    if les.id in vg.afgeronde_lessen:
        return Status.af
    module = cat.modules[les.meta.module]
    if module.id not in vg.beheerste_modules and not module_open(cat, vg, module):
        return Status.op_slot
    if all(_les_voldaan(cat, vg, vereist) for vereist in les.meta.vereist):
        return Status.open
    return Status.op_slot


def ontbrekend(cat: Catalogus, vg: Voortgang, les: Les) -> list[str]:
    """Leesbare uitleg waarom een les op slot zit: wat moet je eerst doen?"""
    redenen = []
    module = cat.modules[les.meta.module]
    if module.id not in vg.beheerste_modules:
        for vereist in module.vereist:
            if not module_voldaan(cat, vg, vereist):
                redenen.append(f"Rond eerst de module '{cat.modules[vereist].titel}' af.")
    for vereist in les.meta.vereist:
        if not _les_voldaan(cat, vg, vereist):
            redenen.append(f"Doe eerst de les '{cat.lessen[vereist].meta.titel}'.")
    return redenen


def volgende_les(cat: Catalogus, vg: Voortgang) -> Les | None:
    """De eerste open les in cursusvolgorde: wat je nu het beste kunt doen."""
    return next((les for les in cat.alle_lessen() if les_status(cat, vg, les) == Status.open), None)
