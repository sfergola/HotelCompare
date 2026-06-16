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
    # solo camera → marker ≈ (la stima colazione la aggiunge normalizza_prezzo)
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale Standard",
        "€ 110",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 110≈"


def test_economy_double():
    page = _page(
        "Tipologia camera",
        "Economy Double",
        "€ 95",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 95#≈"


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


def test_bb_preferita_a_solo_camera():
    # confronto omogeneo doppia+colazione: la B&B reale vince anche se più cara
    # della solo-camera (la solo-camera +stima sarebbe comunque ~€141)
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "€ 140",
        "Prima colazione inclusa",
        "Camera Doppia",
        "€ 125",
        "Solo pernottamento",
    )
    assert estrai_prezzo(page) == "€ 140*"


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


# ── prezzo barrato e sconti ──────────────────────────────────────────────────

def test_prezzo_barrato_prende_attuale():
    # con sconto attivo Booking mostra: barrato, attuale, riga esplicita
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "N° max persone: 2",
        "€ 757",
        "€ 696",
        "Prezzo iniziale € 757 Prezzo attuale € 696",
        "Include tasse e costi",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 696*"


def test_prezzo_barrato_senza_riga_esplicita():
    # anche senza la riga "Prezzo attuale": il barrato è più alto, vince il minimo
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "€ 150",
        "€ 138",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 138*"


def test_colazione_a_pagamento_e_solo_camera():
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "N° max persone: 2",
        "€ 120",
        "Ottima colazione per € 10",
    )
    assert estrai_prezzo(page) == "€ 120≈"


def test_tariffa_singolo_ospite_esclusa():
    # la tariffa "per 1 ospite" della doppia non è il prezzo della doppia
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "N° max persone: 1",
        "Solo per 1 ospite",
        "€ 90",
        "Prima colazione inclusa",
        "N° max persone: 2",
        "€ 130",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 130*"


def test_bb_vince_su_solo_camera_con_colazione_a_pagamento():
    # B&B reale €871 vs solo-camera €1229: vince la B&B (doppia + colazione)
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale",
        "N° max persone: 2",
        "€ 871",
        "Buona colazione inclusa",
        "N° max persone: 2",
        "€ 1229",
        "Buona colazione per € 21",
    )
    assert estrai_prezzo(page) == "€ 871*"


def test_header_tipologia_nudo():
    # alcune strutture usano l'header "Tipologia" senza "camera"
    page = _page(
        "Tipologia\tNumero di ospiti",
        "Camera Matrimoniale",
        "€ 120",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 120*"


def test_riga_camera_nuda_non_sovrascrive_nome():
    # "Camera" da solo è una label di feature, non un nome camera
    page = _page(
        "Tipologia camera",
        "Camera Matrimoniale Vista Mare",
        "Camera",
        "18 m²",
        "N° max persone: 2",
        "€ 140",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 140*"


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


def test_layout_card_esclude_singolo_ospite():
    page = _page(
        "Camera Matrimoniale Comfort",
        "N° max persone: 1",
        "Solo per 1 ospite",
        "€ 95",
        "Prima colazione inclusa",
        "N° max persone: 2",
        "€ 135",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 135*"


def test_layout_card_prezzo_barrato():
    page = _page(
        "Camera Matrimoniale Comfort",
        "N° max persone: 2",
        "€ 150",
        "€ 138",
        "Prezzo iniziale € 150 Prezzo attuale € 138",
        "Prima colazione inclusa",
    )
    assert estrai_prezzo(page) == "€ 138*"


# ── pagine reali Booking (dump del 10/06/2026, verificati a mano) ───────────

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_page(nome: str) -> FakePage:
    return FakePage((FIXTURES / nome).read_text(encoding="utf-8"))


def test_pagina_reale_lido_inn_sconto_8pct():
    # 3 notti 08/08: la matrimoniale standard ha due tariffe — € 696 solo camera
    # (colazione a € 10) e € 724 "colazione inclusa". Vince la B&B reale (doppia +
    # colazione vera), più accurata della stima ≈.
    assert estrai_prezzo(_fixture_page("Hotel_Lido_Inn_2026-08-08_3n.txt")) == "€ 724*"


def test_pagina_reale_capri_header_nudo_e_tariffa_1_ospite():
    # header "Tipologia", doppia vera € 871 B&B; la tariffa "Solo per 1 ospite"
    # (€ 827) e la riga-feature "Camera" non devono ingannare il parser
    assert estrai_prezzo(_fixture_page("Hotel_Capri_2026-06-20_5n.txt")) == "€ 871*"


def test_pagina_reale_lido_inn_giugno():
    # 1 notte 20/06: stessa matrimoniale, € 319 solo camera vs € 329 "colazione
    # inclusa" (= 319 + i € 10 di colazione). Vince la B&B reale € 329.
    assert estrai_prezzo(_fixture_page("Hotel_Lido_Inn_2026-06-20.txt")) == "€ 329*"
