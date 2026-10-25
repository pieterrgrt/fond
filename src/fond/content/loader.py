"""Leest `content/` in, valideert alles en bouwt er een `Catalogus` van.

De catalogus staat in het geheugen: inhoud verandert alleen via git en een herstart,
dus een database is daarvoor niet nodig.
"""

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import yaml
from pydantic import ValidationError

from fond.content.models import (
    Afdeling,
    Cursus,
    Ingredient,
    Les,
    LesMeta,
    Module,
    Niveau,
    Sectie,
    Techniek,
)

VERPLICHTE_SECTIES = ("Theorie", "Techniek")
_TERM = re.compile(r"\[\[([a-z0-9-]+)(?:\|([^\]]+))?\]\]")


class InhoudFout(Exception):
    """Een of meer fouten in de inhoud. `fouten` bevat leesbare meldingen."""

    def __init__(self, fouten: list[str]):
        self.fouten = fouten
        super().__init__("Fouten in de inhoud:\n" + "\n".join(f"- {f}" for f in fouten))


@dataclass
class Catalogus:
    niveaus: list[Niveau]
    modules: dict[str, Module]
    module_niveau: dict[str, Niveau]
    lessen: dict[str, Les]
    afdelingen: list[Afdeling]
    ingredienten: dict[str, Ingredient]
    technieken: dict[str, Techniek]
    # Lessen per module, gesorteerd op volgorde.
    lessen_per_module: dict[str, list[Les]] = field(default_factory=dict)
    # In welke les een techniek voor het eerst wordt aangeleerd.
    techniek_bron: dict[str, str] = field(default_factory=dict)

    def alle_lessen(self) -> list[Les]:
        """Alle lessen in cursusvolgorde: niveau, module, volgorde."""
        return [
            les
            for niveau in self.niveaus
            for module in niveau.modules
            for les in self.lessen_per_module.get(module.id, [])
        ]

    def module_van(self, les: Les) -> Module:
        return self.modules[les.meta.module]

    def niveau_van(self, les: Les) -> Niveau:
        return self.module_niveau[les.meta.module]


def _lees_yaml(pad: Path, fouten: list[str]) -> object:
    try:
        return yaml.safe_load(pad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fouten.append(f"{pad.name}: bestand ontbreekt")
    except yaml.YAMLError as exc:
        fouten.append(f"{pad.name}: ongeldige YAML ({exc})")
    return None


def _validatiefouten(bron: str, exc: ValidationError) -> list[str]:
    return [
        f"{bron}: {'.'.join(str(p) for p in err['loc']) or '(bestand)'}: {err['msg']}"
        for err in exc.errors()
    ]


def splits_frontmatter(tekst: str) -> tuple[str, str]:
    """Splitst '---\\nyaml\\n---\\nmarkdown' in (yaml, markdown)."""
    if not tekst.startswith("---"):
        raise ValueError("frontmatter ontbreekt: het bestand moet met '---' beginnen")
    delen = re.split(r"^---\s*$", tekst, maxsplit=2, flags=re.MULTILINE)
    if len(delen) < 3:
        raise ValueError("frontmatter wordt niet afgesloten met '---'")
    return delen[1], delen[2]


def splits_secties(body: str) -> list[tuple[str, str]]:
    """Deelt de Markdown op in secties per kop van niveau 2 (`## Theorie`)."""
    secties: list[tuple[str, str]] = []
    huidige: str | None = None
    regels: list[str] = []
    for regel in body.splitlines():
        if regel.startswith("## "):
            if huidige is not None:
                secties.append((huidige, "\n".join(regels).strip()))
            huidige, regels = regel[3:].strip(), []
        elif huidige is not None:
            regels.append(regel)
    if huidige is not None:
        secties.append((huidige, "\n".join(regels).strip()))
    return secties


def render_markdown(tekst: str, technieken: dict[str, Techniek]) -> str:
    """Markdown naar HTML; `[[julienne]]` wordt een link naar de woordenlijst."""

    def term(match: re.Match[str]) -> str:
        techniek = technieken[match.group(1)]
        label = match.group(2) or techniek.frans or techniek.naam
        return (
            f'<a class="term" href="/woordenlijst#{techniek.id}" '
            f'title="{html.escape(techniek.uitleg)}">{html.escape(label)}</a>'
        )

    return markdown.markdown(_TERM.sub(term, tekst), extensions=["extra", "sane_lists"])


def laad_catalogus(content_dir: Path) -> Catalogus:
    fouten: list[str] = []

    # Winkel, ingrediënten en technieken.
    afdelingen: list[Afdeling] = []
    ruw = _lees_yaml(content_dir / "winkel.yaml", fouten)
    for i, item in enumerate((ruw or {}).get("afdelingen", [])):
        try:
            afdelingen.append(Afdeling.model_validate(item))
        except ValidationError as exc:
            fouten += _validatiefouten(f"winkel.yaml afdeling {i + 1}", exc)
    afdeling_ids = {a.id for a in afdelingen}

    def lees_lijst(bestand: str, model):
        resultaat = {}
        data = _lees_yaml(content_dir / bestand, fouten) or {}
        for sleutel, waarden in data.items():
            try:
                obj = model.model_validate({"id": sleutel, **(waarden or {})})
            except ValidationError as exc:
                fouten.extend(_validatiefouten(f"{bestand} '{sleutel}'", exc))
                continue
            resultaat[sleutel] = obj
        return resultaat

    ingredienten: dict[str, Ingredient] = lees_lijst("ingredienten.yaml", Ingredient)
    for ing in ingredienten.values():
        if ing.afdeling not in afdeling_ids:
            fouten.append(f"ingredienten.yaml '{ing.id}': onbekende afdeling '{ing.afdeling}'")
    technieken: dict[str, Techniek] = lees_lijst("technieken.yaml", Techniek)

    # Niveaus en modules.
    cursus = Cursus(niveaus=[])
    try:
        cursus = Cursus.model_validate(_lees_yaml(content_dir / "cursus.yaml", fouten) or {})
    except ValidationError as exc:
        fouten += _validatiefouten("cursus.yaml", exc)
    modules: dict[str, Module] = {}
    module_niveau: dict[str, Niveau] = {}
    for niveau in cursus.niveaus:
        for module in niveau.modules:
            if module.id in modules:
                fouten.append(f"cursus.yaml: module-id '{module.id}' komt twee keer voor")
            modules[module.id] = module
            module_niveau[module.id] = niveau
    for module in modules.values():
        for vereist in module.vereist:
            if vereist not in modules:
                fouten.append(f"cursus.yaml '{module.id}': vereist onbekende module '{vereist}'")

    # Lessen.
    lessen: dict[str, Les] = {}
    niveau_ids = {n.id for n in cursus.niveaus}
    for pad in sorted(content_dir.glob("*/*.md")):
        bron = str(pad.relative_to(content_dir))
        if pad.parent.name not in niveau_ids:
            fouten.append(f"{bron}: map '{pad.parent.name}' is geen niveau uit cursus.yaml")
            continue
        try:
            fm, body = splits_frontmatter(pad.read_text(encoding="utf-8"))
            meta = LesMeta.model_validate(yaml.safe_load(fm))
        except ValidationError as exc:
            fouten += _validatiefouten(bron, exc)
            continue
        except (ValueError, yaml.YAMLError) as exc:
            fouten.append(f"{bron}: {exc}")
            continue

        les_fouten = _controleer_les(meta, bron, modules, module_niveau, pad.parent.name,
                                     ingredienten, technieken)
        ruwe_secties = splits_secties(body)
        titels = [t for t, _ in ruwe_secties]
        for verplicht in VERPLICHTE_SECTIES:
            if verplicht not in titels:
                les_fouten.append(f"{bron}: sectie '## {verplicht}' ontbreekt")
        for _, tekst in ruwe_secties:
            for match in _TERM.finditer(tekst):
                if match.group(1) not in technieken:
                    les_fouten.append(f"{bron}: [[{match.group(1)}]] staat niet in technieken.yaml")
        if meta.id in lessen:
            les_fouten.append(f"{bron}: les-id '{meta.id}' bestaat al ({lessen[meta.id].bestand})")
        if les_fouten:
            fouten += les_fouten
            continue

        secties = [Sectie(titel=t, html=render_markdown(x, technieken)) for t, x in ruwe_secties]
        lessen[meta.id] = Les(meta=meta, bestand=bron, secties=secties)

    catalogus = Catalogus(
        niveaus=cursus.niveaus,
        modules=modules,
        module_niveau=module_niveau,
        lessen=lessen,
        afdelingen=afdelingen,
        ingredienten=ingredienten,
        technieken=technieken,
    )
    for module_id in modules:
        rij = sorted((les for les in lessen.values() if les.meta.module == module_id),
                     key=lambda les: les.meta.volgorde)
        volgordes = [les.meta.volgorde for les in rij]
        if len(set(volgordes)) != len(volgordes):
            fouten.append(f"module '{module_id}': twee lessen met dezelfde volgorde")
        catalogus.lessen_per_module[module_id] = rij

    fouten += _controleer_samenhang(catalogus)
    if fouten:
        raise InhoudFout(fouten)
    return catalogus


def _controleer_les(meta: LesMeta, bron: str, modules, module_niveau, map_naam,
                    ingredienten, technieken) -> list[str]:
    fouten = []
    if meta.module not in modules:
        return [f"{bron}: onbekende module '{meta.module}'"]
    if module_niveau[meta.module].id != map_naam:
        fouten.append(f"{bron}: module '{meta.module}' hoort niet bij niveau '{map_naam}'")
    for t in meta.technieken + meta.herhaalt:
        if t not in technieken:
            fouten.append(f"{bron}: techniek '{t}' staat niet in technieken.yaml")
    if meta.recept:
        for ing in meta.recept.ingredienten:
            if ing.item not in ingredienten:
                fouten.append(f"{bron}: ingrediënt '{ing.item}' staat niet in ingredienten.yaml")
            if (ing.hoeveelheid is None) != (ing.eenheid is None):
                fouten.append(
                    f"{bron}: ingrediënt '{ing.item}': geef hoeveelheid én eenheid, of geen "
                    "van beide (naar smaak)"
                )
    return fouten


def _controleer_samenhang(cat: Catalogus) -> list[str]:
    """Controles over lessen heen: verwijzingen, kringen en de herhaal-volgorde."""
    fouten = []
    for les in cat.lessen.values():
        for vereist in les.meta.vereist:
            if vereist not in cat.lessen:
                fouten.append(f"{les.bestand}: vereist onbekende les '{vereist}'")

    # Geen kringen in `vereist` (anders gaat een les nooit open).
    def kring(start: str, pad: tuple[str, ...]) -> bool:
        for volgende in cat.lessen[start].meta.vereist:
            if volgende in pad or (volgende in cat.lessen and kring(volgende, pad + (volgende,))):
                return True
        return False

    for les_id in cat.lessen:
        if kring(les_id, (les_id,)):
            fouten.append(f"les '{les_id}': 'vereist' vormt een kring")

    # Een techniek wordt aangeleerd in de eerste les die hem in `technieken` noemt;
    # `herhaalt` mag alleen naar technieken die eerder in de cursus zijn aangeleerd.
    for les in cat.alle_lessen():
        for t in les.meta.herhaalt:
            if t not in cat.techniek_bron:
                fouten.append(f"{les.bestand}: herhaalt '{t}', maar die is nog niet aangeleerd")
        for t in les.meta.technieken:
            cat.techniek_bron.setdefault(t, les.id)
    return fouten
