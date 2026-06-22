"""
Smoke test LIVE (rete) — verifica che il parser estragga ANCORA un numero da Booking.

Cosa controlla: su un campione di hotel con data vicina (dove la disponibilità è
probabile), almeno uno deve restituire un prezzo. Becca la *rottura silenziosa*
(parser che non legge più nulla → tutte le celle vuote).

Cosa NON controlla: il prezzo esatto (cambia ogni giorno) e i *misread sistematici*
(parser che legge sempre il numero sbagliato allo stesso modo, es. il prezzo
barrato). Quelli li vede solo l'occhio umano aprendo Booking → `scripts/spotcheck.py`.

ESCLUSO di default (marker `network`). Lancia con:  pytest -m network
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


@pytest.mark.network
def test_parser_estrae_un_numero_dal_vivo():
    from playwright.sync_api import sync_playwright
    from scraper import scrapa_query

    cfg = json.loads((ROOT / "competitors.json").read_text())
    urls = {c["nome"]: c["booking_url"] for c in cfg["competitor"] if c.get("booking_url")}
    adulti = cfg.get("adulti", 2)
    campione = list(urls.items())[:3]           # 3 hotel
    checkin = date.today() + timedelta(days=10)  # data vicina: disponibilità probabile

    prezzi = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA, locale="it-IT",
                                   viewport={"width": 1280, "height": 900}).new_page()
        for _nome, url in campione:
            if scrapa_query(page, url, checkin, 1, adulti)["prezzo"]:
                prezzi += 1
        browser.close()

    assert prezzi > 0, (
        "Nessun prezzo estratto dal vivo su 3 hotel con data vicina: "
        "il parser probabilmente non legge più Booking (rottura silenziosa)."
    )
