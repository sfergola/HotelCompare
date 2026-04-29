"""Debug veloce: un solo hotel, dumpa contesto intorno ai prezzi e alla tabella camere."""
import time, sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright

cfg  = json.loads((Path(__file__).parent / "competitors.json").read_text())
NOME = sys.argv[1] if len(sys.argv) > 1 else "Hotel Sirio"
CHECKIN  = "2026-06-07"
CHECKOUT = "2026-06-14"

comp = next((c for c in cfg["competitor"] if c["nome"] == NOME), None)
if not comp or "booking_url" not in comp:
    print(f"Hotel '{NOME}' non trovato o senza URL")
    sys.exit(1)

url = comp["booking_url"] + f"?checkin={CHECKIN}&checkout={CHECKOUT}&group_adults=2&no_rooms=1&selected_currency=EUR"
print(f"URL: {url}\n")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="it-IT", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=40000)
    time.sleep(5)
    page.evaluate("window.scrollTo(0, 1200)")
    time.sleep(2)

    testo = page.inner_text("body")
    tl    = testo.lower()

    print(f"Titolo: {page.title()}")
    print(f"Lunghezza testo: {len(testo)} caratteri")
    print(f"Ha 'strutture simili': {'strutture simili' in tl}")
    print()

    # Header tabella
    for kw in ["Tipologia camera", "tipo di camera", "room type"]:
        if kw.lower() in tl:
            idx = tl.find(kw.lower())
            print(f"=== Header '{kw}' trovato a pos {idx} ===")
            print(repr(testo[idx : idx + 600]))
            print()
            break
    else:
        print("=== Nessun header tabella camere trovato ===")
        # Dumpa le prime 2000 righe non vuote per vedere cosa c'è
        righe = [r.strip() for r in testo.split("\n") if r.strip()][:80]
        print("\n".join(righe))

    # Keywords colazione
    print("\n=== Keywords pensione ===")
    for kw in ["colazione inclusa", "prima colazione", "eccezionale colazione",
               "buona colazione", "solo pernottamento", "b&b", "room only"]:
        if kw in tl:
            idx = tl.find(kw)
            print(f"  '{kw}': {repr(testo[idx:idx+80])}")

    browser.close()
