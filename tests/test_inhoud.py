from pathlib import Path

import pytest

from fond.config import PROJECT_ROOT
from fond.content.loader import InhoudFout, laad_catalogus
from fond.content.models import parse_duur
from tests.conftest import les, schrijf_inhoud


def test_echte_inhoud_is_geldig():
    """De inhoud in de repo moet altijd door de validatie komen."""
    cat = laad_catalogus(PROJECT_ROOT / "content")
    assert "mise-en-place" in cat.lessen
    for les_ in cat.alle_lessen():
        assert les_.sectie("Theorie") and les_.sectie("Techniek")


def test_catalogus_volgorde_en_bronnen(cat):
    assert [x.id for x in cat.alle_lessen()] == ["a", "b", "c"]
    assert cat.techniek_bron == {"snijden": "a", "koken": "b", "bakken": "c"}
    assert 'href="/woordenlijst#snijden"' in cat.lessen["a"].sectie("Theorie").html


@pytest.mark.parametrize(
    "tekst,seconden", [("10m", 600), ("1u30m", 5400), ("45s", 45), ("2u", 7200)]
)
def test_parse_duur(tekst, seconden):
    assert parse_duur(tekst) == seconden


@pytest.mark.parametrize("fout", ["", "10", "tien minuten", "5x"])
def test_parse_duur_fout(fout):
    with pytest.raises(ValueError):
        parse_duur(fout)


def fouten_bij(tmp_path: Path, lessen: dict[str, str]) -> list[str]:
    with pytest.raises(InhoudFout) as exc:
        laad_catalogus(schrijf_inhoud(tmp_path / "c", lessen))
    return exc.value.fouten


def test_onbekend_ingredient_en_techniek(tmp_path):
    tekst = les("a", "basis", 1, technieken=["vliegen"]).replace("item: rijst", "item: kaviaar")
    fouten = fouten_bij(tmp_path, {"01-a.md": tekst})
    assert any("vliegen" in f for f in fouten)
    assert any("kaviaar" in f for f in fouten)


def test_tikfout_in_veldnaam(tmp_path):
    tekst = les("a", "basis", 1).replace("hoeveelheid: 200", "hoeveelheit: 200")
    assert any("hoeveelheit" in f for f in fouten_bij(tmp_path, {"01-a.md": tekst}))


def test_ontbrekende_sectie(tmp_path):
    tekst = les("a", "basis", 1).replace("## Techniek", "## Iets anders")
    assert any("Techniek" in f for f in fouten_bij(tmp_path, {"01-a.md": tekst}))


def test_herhalen_voordat_aangeleerd(tmp_path):
    fouten = fouten_bij(
        tmp_path,
        {
            "01-a.md": les("a", "basis", 1, herhaalt=["koken"]),
            "02-b.md": les("b", "basis", 2, technieken=["koken"]),
        },
    )
    assert any("nog niet aangeleerd" in f for f in fouten)


def test_kring_in_vereist(tmp_path):
    fouten = fouten_bij(
        tmp_path,
        {
            "01-a.md": les("a", "basis", 1, vereist=["b"]),
            "02-b.md": les("b", "basis", 2, vereist=["a"]),
        },
    )
    assert any("kring" in f for f in fouten)


def test_dubbele_id_en_verkeerde_timer(tmp_path):
    fouten = fouten_bij(
        tmp_path,
        {
            "01-a.md": les("a", "basis", 1),
            "02-a.md": les("a", "basis", 2).replace("timer: 12m", "timer: twaalf"),
        },
    )
    assert any("timer" in f for f in fouten)


def test_les_in_verkeerde_niveaumap(tmp_path):
    map_ = schrijf_inhoud(tmp_path / "c", {"01-a.md": les("a", "basis", 1)})
    (map_ / "twee").mkdir()
    (map_ / "twee" / "01-x.md").write_text(les("x", "basis", 2))
    with pytest.raises(InhoudFout) as exc:
        laad_catalogus(map_)
    assert any("geen niveau" in f for f in exc.value.fouten)
