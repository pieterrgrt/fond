from fond.voortgang import (
    Status,
    Voortgang,
    les_status,
    module_status,
    ontbrekend,
    volgende_les,
)


def vg(lessen=(), beheerst=()):
    return Voortgang(frozenset(lessen), frozenset(beheerst))


def test_begin(cat):
    v = vg()
    assert les_status(cat, v, cat.lessen["a"]) == Status.open
    assert les_status(cat, v, cat.lessen["b"]) == Status.op_slot  # vereist a
    assert les_status(cat, v, cat.lessen["c"]) == Status.op_slot  # module vervolg dicht
    assert module_status(cat, v, cat.modules["basis"]) == Status.open
    assert module_status(cat, v, cat.modules["leeg"]) == Status.binnenkort
    assert volgende_les(cat, v).id == "a"


def test_na_eerste_les(cat):
    v = vg(["a"])
    assert les_status(cat, v, cat.lessen["a"]) == Status.af
    assert les_status(cat, v, cat.lessen["b"]) == Status.open
    assert module_status(cat, v, cat.modules["basis"]) == Status.bezig
    assert les_status(cat, v, cat.lessen["c"]) == Status.op_slot


def test_module_af_opent_vervolg(cat):
    v = vg(["a", "b"])
    assert module_status(cat, v, cat.modules["basis"]) == Status.af
    assert les_status(cat, v, cat.lessen["c"]) == Status.open
    assert volgende_les(cat, v).id == "c"


def test_beheerst_slaat_module_over(cat):
    v = vg(beheerst=["basis"])
    assert module_status(cat, v, cat.modules["basis"]) == Status.beheerst
    assert les_status(cat, v, cat.lessen["c"]) == Status.open
    # Lessen in een beheerste module blijven gewoon te doen.
    assert les_status(cat, v, cat.lessen["b"]) == Status.open


def test_niet_lineair_binnen_module(cat):
    """Zonder `vereist` mag je binnen een module in elke volgorde."""
    v = vg()
    cat.lessen["b"].meta.vereist.clear()
    assert les_status(cat, v, cat.lessen["b"]) == Status.open


def test_uitleg_waarom_op_slot(cat):
    redenen = ontbrekend(cat, vg(), cat.lessen["c"])
    assert redenen == ["Rond eerst de module 'Basis' af."]
    assert ontbrekend(cat, vg(), cat.lessen["b"]) == ["Doe eerst de les 'Les a'."]


def test_lege_module_kan_niet_voldaan_zijn(cat):
    assert volgende_les(cat, vg(["a", "b", "c"])) is None
