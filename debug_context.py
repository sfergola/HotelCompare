"""Stampa contesto (±20 righe) intorno a 'colazione inclusa' e ai prezzi €."""
import time, sys, json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

EURO_RE = re.compile(r"€\s*(\d+(?:[.,]\d+)?)")
cfg  = json.loads((Path(__file__).parent / "competitors.json").read_text())
NOME = sys.argv[1] if len(sys.argv) > 1 else "Hotel Sirio"
CHECKIN  = "2026-06-07"
CHECKOUT = "2026-06-14"

comp = next((c for c in cfg["competitor"] if c["nome"] == NOME), None)
url = comp["booking_url"] + f"?checkin={CHECKIN}&checkout={CHECKOUT}&group_adults=2&no_rooms=1&selected_currency=EUR"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="it-IT", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto(url, wait_until="networkidle", timeout=40000)
    time.sleep(3)
    page.evaluate("window.scrollTo(0, 2000)")
    time.sleep(2)

    testo = page.inner_text("body")
    righe = [r.strip() for r in testo.split("\n") if r.strip()]
    browser.close()

print(f"Totale righe non vuote: {len(righe)}")

# Cerca righe con € e contesto
print("\n=== Righe con € (con ±3 righe contesto) ===")
for i, r in enumerate(righe):
    if EURO_RE.search(r):
        start = max(0, i-3)
        end   = min(len(righe), i+4)
        print(f"--- posizione {i} ---")
        for j in range(start, end):
            marker = ">>>" if j == i else "   "
            print(f"{marker} [{j}] {righe[j]}")
        print()

# Cerca righe con colazione
print("\n=== Righe con 'colazione' ===")
for i, r in enumerate(righe):
    if "colazione" in r.lower():
        start = max(0, i-5)
        end   = min(len(righe), i+3)
        print(f"--- posizione {i} ---")
        for j in range(start, end):
            marker = ">>>" if j == i else "   "
            print(f"{marker} [{j}] {righe[j]}")
        print()
