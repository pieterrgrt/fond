"""Alle pagina's van Fond.

Server-rendered: elke route geeft HTML terug. HTMX ververst kleine stukjes (een
vinkje, een portiekeuze) zonder de hele pagina te herladen.
"""

import hashlib
import re
import uuid
from collections.abc import Iterator
from datetime import date
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from fond.auth import controleer_wachtwoord, veilige_volgende
from fond.boodschappen import maak_lijst
from fond.content.loader import Catalogus
from fond.content.models import Les
from fond.db import BeheersteModule, LijstItem, Reflectie, Vinkje
from fond.herhaling import te_herhalen
from fond.schalen import schaal_recept
from fond.voortgang import Status, Voortgang, les_status, module_status, ontbrekend, volgende_les
from fond.web.templates import STATIC, templates

router = APIRouter()

PORTIE_KEUZES = (1, 2, 3, 4, 6)
MAX_FOTO = 15 * 1024 * 1024
FOTO_NAAM = re.compile(r"^[0-9a-f]{32}\.jpg$")


# --- Afhankelijkheden -------------------------------------------------------------


def catalogus(request: Request) -> Catalogus:
    return request.app.state.catalogus


def db(request: Request) -> Iterator[Session]:
    with request.app.state.sessies() as sessie:
        yield sessie


Cat = Annotated[Catalogus, Depends(catalogus)]
Db = Annotated[Session, Depends(db)]


def laad_voortgang(sessie: Session) -> Voortgang:
    return Voortgang(
        afgeronde_lessen=frozenset(sessie.scalars(select(Reflectie.les_id).distinct())),
        beheerste_modules=frozenset(sessie.scalars(select(BeheersteModule.module_id))),
    )


def vind_les(cat: Catalogus, les_id: str) -> Les:
    les = cat.lessen.get(les_id)
    if les is None:
        raise HTTPException(404, "Deze les bestaat niet.")
    return les


def punt_id(tekst: str) -> str:
    return hashlib.sha1(tekst.encode()).hexdigest()[:12]


def kies_porties(les: Les, porties: int | None) -> int:
    standaard = les.meta.recept.porties if les.meta.recept else 1
    return min(max(porties or standaard, 1), 12)


def render(request: Request, naam: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, naam, context)


# --- Inloggen ---------------------------------------------------------------------


@router.get("/login")
def login_pagina(request: Request, volgende: str = "/"):
    return render(request, "login.html", volgende=veilige_volgende(volgende), fout=None)


@router.post("/login")
def login(
    request: Request, wachtwoord: Annotated[str, Form()], volgende: Annotated[str, Form()] = "/"
):
    pogingen = request.app.state.pogingen
    ip = request.client.host if request.client else "?"
    if pogingen.geblokkeerd(ip):
        return render(
            request,
            "login.html",
            volgende=volgende,
            fout="Te veel pogingen. Probeer het over een kwartier opnieuw.",
        )
    if not controleer_wachtwoord(wachtwoord, request.app.state.settings.password_hash):
        pogingen.mislukt(ip)
        return render(request, "login.html", volgende=volgende, fout="Dat wachtwoord klopt niet.")
    pogingen.gelukt(ip)
    request.session.clear()
    request.session["ingelogd"] = True
    return RedirectResponse(veilige_volgende(volgende), status_code=303)


@router.post("/uitloggen")
def uitloggen(request: Request):
    request.session.clear()
    return RedirectResponse("/login?uitgelogd=1", status_code=303)


@router.get("/gezond")
def gezond():
    return {"status": "ok"}


# --- Cursusoverzicht --------------------------------------------------------------


@router.get("/")
def overzicht(request: Request, cat: Cat, sessie: Db, melding: str | None = None):
    vg = laad_voortgang(sessie)
    gekookt = sessie.execute(select(Reflectie.les_id, Reflectie.gekookt_op)).all()
    open_lessen = {les.id for les in cat.alle_lessen() if les_status(cat, vg, les) == Status.open}
    niveaus = []
    for niveau in cat.niveaus:
        modules = []
        for module in niveau.modules:
            lessen = [
                (les, les_status(cat, vg, les)) for les in cat.lessen_per_module.get(module.id, [])
            ]
            modules.append((module, module_status(cat, vg, module), lessen))
        totaal = sum(len(m[2]) for m in modules)
        klaar = sum(1 for m in modules for _, s in m[2] if s == Status.af)
        niveaus.append((niveau, modules, klaar, totaal))
    return render(
        request,
        "overzicht.html",
        niveaus=niveaus,
        volgende=volgende_les(cat, vg),
        herhalingen=te_herhalen(cat, gekookt, date.today(), open_lessen)[:3],
        aantal_af=len(vg.afgeronde_lessen),
        melding=melding,
        Status=Status,
    )


@router.post("/module/{module_id}/beheerst")
def module_beheerst(
    cat: Cat, sessie: Db, module_id: str, uitspraak: Annotated[list[str] | None, Form()] = None
):
    module = cat.modules.get(module_id)
    if module is None:
        raise HTTPException(404)
    if not module.zelftoets or len(set(uitspraak or [])) < len(module.zelftoets):
        return RedirectResponse(f"/?melding=zelftoets#module-{module_id}", status_code=303)
    if sessie.get(BeheersteModule, module_id) is None:
        sessie.add(BeheersteModule(module_id=module_id))
        sessie.commit()
    return RedirectResponse(f"/#module-{module_id}", status_code=303)


@router.post("/module/{module_id}/intrekken")
def module_intrekken(sessie: Db, module_id: str):
    if (rij := sessie.get(BeheersteModule, module_id)) is not None:
        sessie.delete(rij)
        sessie.commit()
    return RedirectResponse(f"/#module-{module_id}", status_code=303)


# --- Lessen -----------------------------------------------------------------------


def les_context(cat: Catalogus, sessie: Session, les: Les, porties: int) -> dict:
    vg = laad_voortgang(sessie)
    recept = les.meta.recept
    geschaald = schaal_recept(recept, cat.ingredienten, porties) if recept else []
    groepen: dict[str | None, list] = {}
    for regel in geschaald:
        groepen.setdefault(regel.bron.groep, []).append(regel)
    vinkjes = set(sessie.scalars(select(Vinkje.punt).where(Vinkje.les_id == les.id)))
    alle = cat.alle_lessen()
    index = alle.index(les)
    return {
        "les": les,
        "module": cat.module_van(les),
        "niveau": cat.niveau_van(les),
        "status": les_status(cat, vg, les),
        "ontbrekend": ontbrekend(cat, vg, les),
        "porties": porties,
        "portie_keuzes": sorted({*PORTIE_KEUZES, porties}),
        "ingredient_groepen": groepen,
        "opdracht": [(punt_id(t), t, punt_id(t) in vinkjes) for t in les.meta.opdracht],
        "technieken": [cat.technieken[t] for t in les.meta.technieken],
        "herhaalt": [
            (cat.technieken[t], cat.lessen[cat.techniek_bron[t]]) for t in les.meta.herhaalt
        ],
        "reflecties": sessie.scalars(
            select(Reflectie)
            .where(Reflectie.les_id == les.id)
            .order_by(Reflectie.gekookt_op.desc())
        ).all(),
        "op_lijst": sessie.get(LijstItem, les.id),
        "vorige": alle[index - 1] if index > 0 else None,
        "volgende": alle[index + 1] if index + 1 < len(alle) else None,
        "Status": Status,
        "vandaag": date.today(),
    }


@router.get("/les/{les_id}")
def les_pagina(
    request: Request,
    cat: Cat,
    sessie: Db,
    les_id: str,
    porties: Annotated[int | None, Query()] = None,
    afgerond: bool = False,
):
    les = vind_les(cat, les_id)
    context = les_context(cat, sessie, les, kies_porties(les, porties))
    vg = laad_voortgang(sessie)
    context["afgerond"] = afgerond
    context["daarna"] = volgende_les(cat, vg) if afgerond else None
    return render(request, "les.html", **context)


@router.post("/les/{les_id}/vinkje/{punt}")
def vinkje(request: Request, cat: Cat, sessie: Db, les_id: str, punt: str):
    les = vind_les(cat, les_id)
    teksten = {punt_id(t): t for t in les.meta.opdracht}
    if punt not in teksten:
        raise HTTPException(404)
    bestaand = sessie.get(Vinkje, (les_id, punt))
    if bestaand:
        sessie.delete(bestaand)
    else:
        sessie.add(Vinkje(les_id=les_id, punt=punt))
    sessie.commit()
    return render(
        request,
        "partials/vinkje.html",
        les=les,
        punt=punt,
        tekst=teksten[punt],
        aan=bestaand is None,
    )


@router.get("/les/{les_id}/koken")
def kookmodus(
    request: Request,
    cat: Cat,
    sessie: Db,
    les_id: str,
    porties: Annotated[int | None, Query()] = None,
):
    les = vind_les(cat, les_id)
    if les.meta.recept is None:
        return RedirectResponse(f"/les/{les_id}", status_code=303)
    return render(
        request, "koken.html", **les_context(cat, sessie, les, kies_porties(les, porties))
    )


# --- Reflectie (proeven) en logboek -----------------------------------------------


def bewaar_foto(foto: UploadFile, map_) -> str | None:
    """Verkleint de foto, draait hem rechtop en verwijdert de EXIF-gegevens
    (daarin staat vaak je GPS-locatie)."""
    inhoud = foto.file.read(MAX_FOTO + 1)
    if not inhoud:
        return None
    if len(inhoud) > MAX_FOTO:
        raise HTTPException(413, "Die foto is te groot (maximaal 15 MB).")
    try:
        beeld = ImageOps.exif_transpose(Image.open(BytesIO(inhoud)))
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(400, "Dat bestand is geen foto die ik kan lezen.") from exc
    beeld = beeld.convert("RGB")
    beeld.thumbnail((1600, 1600))
    naam = f"{uuid.uuid4().hex}.jpg"
    beeld.save(map_ / naam, "JPEG", quality=82, optimize=True)
    return naam


@router.post("/les/{les_id}/reflectie")
def reflectie(
    request: Request,
    cat: Cat,
    sessie: Db,
    les_id: str,
    cijfer: Annotated[int, Form(ge=1, le=10)],
    gekookt_op: Annotated[date, Form()],
    porties: Annotated[int, Form(ge=1, le=12)] = 1,
    wat_lukte: Annotated[str, Form()] = "",
    wat_niet: Annotated[str, Form()] = "",
    volgende_keer: Annotated[str, Form()] = "",
    foto: Annotated[UploadFile | None, File()] = None,
):
    les = vind_les(cat, les_id)
    if les_status(cat, laad_voortgang(sessie), les) == Status.op_slot:
        raise HTTPException(403, "Deze les zit nog op slot.")
    naam = (
        bewaar_foto(foto, request.app.state.settings.foto_dir) if foto and foto.filename else None
    )
    sessie.add(
        Reflectie(
            les_id=les_id,
            cijfer=cijfer,
            gekookt_op=gekookt_op,
            porties=porties,
            wat_lukte=wat_lukte.strip(),
            wat_niet=wat_niet.strip(),
            volgende_keer=volgende_keer.strip(),
            foto=naam,
        )
    )
    sessie.commit()
    return RedirectResponse(f"/les/{les_id}?afgerond=1#proeven", status_code=303)


@router.post("/reflectie/{reflectie_id}/verwijderen")
def reflectie_verwijderen(request: Request, sessie: Db, reflectie_id: int):
    rij = sessie.get(Reflectie, reflectie_id)
    if rij is None:
        raise HTTPException(404)
    if rij.foto:
        (request.app.state.settings.foto_dir / rij.foto).unlink(missing_ok=True)
    sessie.delete(rij)
    sessie.commit()
    return RedirectResponse("/logboek", status_code=303)


@router.get("/logboek")
def logboek(request: Request, cat: Cat, sessie: Db):
    reflecties = sessie.scalars(
        select(Reflectie).order_by(Reflectie.gekookt_op.desc(), Reflectie.id.desc())
    ).all()
    cijfers = [r.cijfer for r in reflecties]
    return render(
        request,
        "logboek.html",
        reflecties=[(r, cat.lessen.get(r.les_id)) for r in reflecties],
        gemiddeld=round(sum(cijfers) / len(cijfers), 1) if cijfers else None,
    )


@router.get("/foto/{naam}")
def foto(request: Request, naam: str):
    if not FOTO_NAAM.match(naam):
        raise HTTPException(404)
    pad = request.app.state.settings.foto_dir / naam
    if not pad.exists():
        raise HTTPException(404)
    return FileResponse(
        pad,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# --- Boodschappen -----------------------------------------------------------------


@router.get("/boodschappen")
def boodschappen(request: Request, cat: Cat, sessie: Db):
    items = sessie.scalars(select(LijstItem).order_by(LijstItem.toegevoegd)).all()
    keuze = [(cat.lessen[i.les_id], i.porties) for i in items if i.les_id in cat.lessen]
    return render(
        request,
        "boodschappen.html",
        lijst=maak_lijst(cat, keuze),
        eigen=True,
        sleutel=lijst_sleutel(keuze),
    )


@router.get("/les/{les_id}/boodschappen")
def les_boodschappen(
    request: Request, cat: Cat, les_id: str, porties: Annotated[int | None, Query()] = None
):
    les = vind_les(cat, les_id)
    keuze = [(les, kies_porties(les, porties))]
    return render(
        request,
        "boodschappen.html",
        lijst=maak_lijst(cat, keuze),
        eigen=False,
        les=les,
        porties=keuze[0][1],
        sleutel=lijst_sleutel(keuze),
    )


def lijst_sleutel(keuze: list[tuple[Les, int]]) -> str:
    """Verandert als de lijst verandert, zodat afvinken op je telefoon opnieuw begint."""
    tekst = "|".join(f"{les.id}:{p}" for les, p in sorted(keuze, key=lambda x: x[0].id))
    return hashlib.sha1(tekst.encode()).hexdigest()[:10]


@router.post("/boodschappen/toevoegen")
def lijst_toevoegen(
    cat: Cat,
    sessie: Db,
    les_id: Annotated[str, Form()],
    porties: Annotated[int, Form(ge=1, le=12)],
    terug: Annotated[str, Form()] = "/boodschappen",
):
    vind_les(cat, les_id)
    item = sessie.get(LijstItem, les_id)
    if item:
        item.porties = porties
    else:
        sessie.add(LijstItem(les_id=les_id, porties=porties))
    sessie.commit()
    return RedirectResponse(veilige_volgende(terug), status_code=303)


@router.post("/boodschappen/verwijderen")
def lijst_verwijderen(sessie: Db, les_id: Annotated[str, Form()]):
    if (item := sessie.get(LijstItem, les_id)) is not None:
        sessie.delete(item)
        sessie.commit()
    return RedirectResponse("/boodschappen", status_code=303)


@router.post("/boodschappen/leegmaken")
def lijst_leegmaken(sessie: Db):
    for item in sessie.scalars(select(LijstItem)).all():
        sessie.delete(item)
    sessie.commit()
    return RedirectResponse("/boodschappen", status_code=303)


# --- Woordenlijst -----------------------------------------------------------------


@router.get("/woordenlijst")
def woordenlijst(request: Request, cat: Cat):
    termen = sorted(cat.technieken.values(), key=lambda t: (t.frans or t.naam).lower())
    return render(
        request,
        "woordenlijst.html",
        termen=termen,
        bron={t: cat.lessen[les_id] for t, les_id in cat.techniek_bron.items()},
    )


# --- PWA --------------------------------------------------------------------------


@router.get("/sw.js")
def service_worker():
    # Vanaf de root geserveerd, zodat de service worker de hele app mag beheren.
    return FileResponse(
        STATIC / "js" / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"}
    )


@router.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/offline.json")
def offline_lijst(cat: Cat, sessie: Db):
    """Alle pagina's die de service worker vooraf bewaart, zodat ze offline werken:
    elke les die open of af is, met de kookmodus voor 1, 2 en 3 porties."""
    vg = laad_voortgang(sessie)
    urls = ["/", "/boodschappen", "/logboek", "/woordenlijst"]
    for les in cat.alle_lessen():
        if les_status(cat, vg, les) == Status.op_slot:
            continue
        urls.append(f"/les/{les.id}")
        if les.meta.recept:
            standaard = les.meta.recept.porties
            for p in sorted({1, 2, 3, standaard}):
                urls.append(f"/les/{les.id}/koken?porties={p}")
            urls.append(f"/les/{les.id}/boodschappen")
    return JSONResponse({"urls": urls})
