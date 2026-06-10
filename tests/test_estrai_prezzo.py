"""
Unit test per estrai_prezzo (scraper.py) su testi pagina sintetici.
Nessuna rete: si usa un FakePage con inner_text fissato.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import estrai_prezzo


class FakePage:
    def __init__(self, testo: str):
        self._testo = testo

    def inner_text(self, selector: str) -> str:
        return self._testo


def _page(*righe: str) -> FakePage:
    return FakePage("\n".join(righe))


# ── Parser 1: layout tabella ─────────────────────────────────────────────────

def test_matrimoniale_bb():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "€ 120",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 120*"


def test_matrimoniale_solo_camera():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale Standard",
        "€ 110",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 110"


def test_economy_double():
    page = _page(
        "Tipologia camera",
        "Economy Double",
        "€ 95",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 95#"


def test_singola_quando_nessuna_doppia():
    page = _page(
        "Tipologia camera",
        "Camera Singola",
        "€ 70",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 70S*"


def test_tripla_fallback():
    page = _page(
        "Tipologia camera",
        "Camera Tripla",
        "€ 150",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 150T"


def test_board_non_identificata():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "€ 130",
    )
    assert estrai_prezzo(page) == "~€ 130"


def test_min_tra_piu_matrimoniali():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale Vista Mare",
        "€ 160",
        "Prima colazione inclusa",
        "Camera Matrimoniale",
        "€ 120",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 120*"


def test_solo_camera_preferita_a_bb():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "€ 140",
        "Prima colazione inclusa",
        "Camera Doppia",
        "€ 125",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 125"


def test_nessuna_camera():
    page = _page("Testo qualunque", "senza prezzi")
    assert estrai_prezzo(page) is None


def test_appartamento_fallback():
    page = _page(
        "Tipologia appartamento",
        "Appartamento con 2 camere",
        "€ 210",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 210A"


# ── Parser 2: layout card ────────────────────────────────────────────────────

def test_layout_card_max_persone():
    page = _page(
        "Camera Matrimoniale Comfort",
        "N° max persone: 2",
        "Prezzo",
        "€ 135",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 135*"
