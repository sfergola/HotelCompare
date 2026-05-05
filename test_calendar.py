"""
Test rapido del nuovo algoritmo calendario su 2 hotel per 3 giorni.
Usa luglio 2026 dove sappiamo che gli hotel hanno disponibilità.
"""

import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

from scraper import risolvi_urls
from algorithm import scrapa_calendario, giorno_range
from report import genera_csv, genera_report_testo

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DATA_INIZIO = date(2026, 7, 5)   # sabato
DATA_FINE   = date(2026, 7, 15)  # 10 giorni — permette query fino a 7 notti

cfg = json.loads((Path(__file__).parent / "competitors.json").read_text())
cfg_test = {
    "adulti": 2,
    "competitor": [c for c in cfg["competitor"]
                   if c["nome"] in ("Hotel Sirio", "Hotel Dei Tigli", "Hotel Capri")]
}

json_path = OUTPUT_DIR / "test_calendar_inprogress.json"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        locale="it-IT",
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()

    urls, _ = risolvi_urls(page, cfg_test)
    manuali = {c["nome"]: c["nota"] for c in cfg_test["competitor"] if "nota" in c}

    print(f"\n=== Scraping {DATA_INIZIO} → {DATA_FINE} ===\n")
    calendario = scrapa_calendario(page, urls, DATA_INIZIO, DATA_FINE, 2, json_path)
    browser.close()

giorni = [str(g) for g in giorno_range(DATA_INIZIO, DATA_FINE)]
nomi   = list(urls.keys()) + list(manuali.keys())

print("\n=== CSV ===")
print(genera_csv(calendario, nomi, manuali, giorni))
print("\n=== TXT ===")
print(genera_report_testo(calendario, nomi, manuali, giorni))
