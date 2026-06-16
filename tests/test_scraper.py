"""
Unit test per le funzioni pure di scraper.py.
Non richiedono Playwright né connessione di rete.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import parse_valore, is_extra_letti, fmt_storico, lookup_entry, filtra_prezzi_anomali


# ── parse_valore ─────────────────────────────────────────────────────────────

def test_parse_valore_intero():
    assert parse_valore("€ 120") == 120.0

def test_parse_valore_con_asterisco():
    assert parse_valore("€ 120*") == 120.0

def test_parse_valore_con_marker():
    assert parse_valore("€ 85#") == 85.0
    assert parse_valore("€ 200T") == 200.0
    assert parse_valore("€ 150A*") == 150.0

def test_parse_valore_virgola_europea():
    assert parse_valore("€ 1.200") == 1200.0
    assert parse_valore("€ 99,50") == 99.5

def test_parse_valore_tilde():
    assert parse_valore("~€ 110") == 110.0

def test_parse_valore_nessun_euro():
    assert parse_valore("non trovato") is None
    assert parse_valore("—") is None
    assert parse_valore("") is None

def test_parse_valore_con_spazi():
    assert parse_valore("€  75") == 75.0


# ── is_extra_letti ───────────────────────────────────────────────────────────

def test_is_extra_letti_tripla():
    assert is_extra_letti("€ 90T") is True
    assert is_extra_letti("€ 90T*") is True

def test_is_extra_letti_quadrupla():
    assert is_extra_letti("€ 100Q") is True

def test_is_extra_letti_appartamento():
    assert is_extra_letti("€ 110A") is True
    assert is_extra_letti("€ 110A*") is True

def test_is_extra_letti_singola():
    # le singole non sono doppie confrontabili → escluse dalla media
    assert is_extra_letti("€ 120S") is True
    assert is_extra_letti("€ 120S*") is True
    assert is_extra_letti("€ 136S≈") is True

def test_is_extra_letti_standard():
    assert is_extra_letti("€ 120") is False
    assert is_extra_letti("€ 120*") is False
    assert is_extra_letti("€ 136≈") is False    # solo camera + stima colazione = doppia
    assert is_extra_letti("€ 120#") is False
    assert is_extra_letti("€ 120#*") is False
    assert is_extra_letti("€ 120#≈") is False
    assert is_extra_letti("~€ 110") is False

def test_is_extra_letti_con_minimum_stay():
    # formato cella prodotto da lookup_entry: "€ 90T×3"
    assert is_extra_letti("€ 90T×3") is True
    assert is_extra_letti("€ 90Q*×2") is True
    assert is_extra_letti("€ 110A×7") is True
    assert is_extra_letti("€ 120S×2") is True
    assert is_extra_letti("€ 90×3") is False
    assert is_extra_letti("€ 90*×3") is False
    assert is_extra_letti("€ 136≈×3") is False


# ── filtra_prezzi_anomali ────────────────────────────────────────────────────

def test_filtra_outlier_estremo():
    # il caso reale: €888 con gli altri hotel a 120-160
    assert filtra_prezzi_anomali([120, 130, 150, 160, 888]) == [120, 130, 150, 160]

def test_filtra_picco_sincronizzato_sopravvive():
    # weekend-evento: più hotel alti insieme → la mediana sale, nessuna esclusione
    valori = [300, 320, 350, 380, 520]
    assert filtra_prezzi_anomali(valori) == valori

def test_filtra_pochi_valori_non_filtra():
    # con meno di 4 valori non si può distinguere un outlier
    assert filtra_prezzi_anomali([100, 888]) == [100, 888]
    assert filtra_prezzi_anomali([100, 120, 888]) == [100, 120, 888]

def test_filtra_lista_vuota():
    assert filtra_prezzi_anomali([]) == []


# ── fmt_storico ───────────────────────────────────────────────────────────────

def test_fmt_storico_base():
    entry = {"storico_prezzo": "€ 120*", "storico_notti": 1, "storico_data": "2026-04-30"}
    assert fmt_storico(entry) == " (€ 120* · 30/04)"

def test_fmt_storico_soggiorno_lungo():
    entry = {"storico_prezzo": "€ 90", "storico_notti": 3, "storico_data": "2026-05-06"}
    assert fmt_storico(entry) == " (€ 90×3 · 06/05)"

def test_fmt_storico_senza_storico():
    assert fmt_storico({}) == ""
    assert fmt_storico({"storico_prezzo": None}) == ""


# ── lookup_entry ──────────────────────────────────────────────────────────────

def test_lookup_entry_prezzo_presente():
    calendario = {"Hotel Sirio": {"2026-07-01": {"prezzo": "€ 120", "notti": 1, "stato": "ok"}}}
    cella, notti = lookup_entry(calendario, "Hotel Sirio", "2026-07-01")
    assert cella == "€ 120"
    assert notti == 1

def test_lookup_entry_soggiorno_lungo():
    calendario = {"Hotel X": {"2026-07-01": {"prezzo": "€ 90", "notti": 3, "stato": "ok"}}}
    cella, notti = lookup_entry(calendario, "Hotel X", "2026-07-01")
    assert cella == "€ 90×3"
    assert notti == 3

def test_lookup_entry_esaurito():
    calendario = {"Hotel X": {"2026-07-01": {"prezzo": None, "notti": None, "stato": "esaurito"}}}
    cella, notti = lookup_entry(calendario, "Hotel X", "2026-07-01")
    assert cella == "✕"
    assert notti == 0

def test_lookup_entry_esaurito_con_storico():
    calendario = {"Hotel X": {"2026-07-01": {
        "prezzo": None, "notti": None, "stato": "esaurito",
        "storico_prezzo": "€ 100", "storico_notti": 1, "storico_data": "2026-04-30"
    }}}
    cella, _ = lookup_entry(calendario, "Hotel X", "2026-07-01")
    assert cella == "✕ (€ 100 · 30/04)"

def test_lookup_entry_non_trovato():
    calendario = {"Hotel X": {"2026-07-01": {"prezzo": None, "stato": "non_trovato"}}}
    cella, notti = lookup_entry(calendario, "Hotel X", "2026-07-01")
    assert cella == "—"
    assert notti == 0

def test_lookup_entry_giorno_mancante():
    cella, notti = lookup_entry({}, "Hotel X", "2026-07-01")
    assert cella == "—"
    assert notti == 0
