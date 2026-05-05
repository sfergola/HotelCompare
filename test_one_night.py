"""Test veloce: scrapa un giorno su tutti i competitor e mostra risultati."""
import json
from pathlib import Path
from datetime import date
from playwright.sync_api import sync_playwright

from scraper import risolvi_urls
from algorithm import scrapa_giorno

CONFIG_PATH = Path(__file__).parent / "competitors.json"
cfg    = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
adulti = cfg.get("adulti", 2)
giorno = date(2026, 7, 5)  # sabato

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="it-IT", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()

    print("=== Risoluzione URL ===")
    urls, _ = risolvi_urls(page, cfg)

    print(f"\n=== Test prezzi per {giorno} ===")
    for nome, url in urls.items():
        entry = scrapa_giorno(page, url, giorno, adulti, date(2026, 7, 12))
        prezzo = entry.get("prezzo") or f"NON TROVATO ({entry.get('stato')})"
        notti  = entry.get("notti", 1)
        sfx    = f" ×{notti}" if notti > 1 else ""
        print(f"  {nome:<30} {prezzo}{sfx}")

    browser.close()
