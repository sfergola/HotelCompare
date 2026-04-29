"""Test veloce: scrapa una notte su tutti i competitor e mostra risultati."""
import json, sys
from pathlib import Path
from datetime import date
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from compare import carica_config, risolvi_urls, scrapa_notte, genera_report_testo

cfg    = carica_config()
adulti = cfg.get("adulti", 2)
notte  = date(2026, 6, 7)  # sabato

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="it-IT", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()

    print("=== Risoluzione URL ===")
    urls = risolvi_urls(page, cfg)
    manuali = {c["nome"]: c["nota"] for c in cfg["competitor"] if "nota" in c}

    print(f"\n=== Test prezzi matrimoniale B&B per {notte} (query 7 notti, prezzo/notte) ===")
    risultati = []
    for nome, url in urls.items():
        res = scrapa_notte(page, nome, url, notte, adulti, notti=7)
        risultati.append(res)
        stato = res["prezzo"] or f"NON TROVATO ({res['stato']})"
        print(f"  {nome:<30} {stato}")

    browser.close()

print()
print(genera_report_testo(risultati, list(urls.keys()) + list(manuali.keys()), manuali, [str(notte)]))
