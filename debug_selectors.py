"""Debug: testa i selettori prezzo su tutti i competitor non trovati."""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

cfg = json.loads((Path(__file__).parent / "competitors.json").read_text())
DA_TESTARE = ["Hotel Sirio", "Hotel Capri", "Hotel Dei Tigli", "Hotel Mariotti"]
CHECKIN  = "2026-06-07"
CHECKOUT = "2026-06-14"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="it-IT", viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()

    for comp in cfg["competitor"]:
        if comp["nome"] not in DA_TESTARE:
            continue
        url = comp["booking_url"] + f"?checkin={CHECKIN}&checkout={CHECKOUT}&group_adults=2&no_rooms=1&selected_currency=EUR"
        print(f"\n{'='*60}")
        print(f"{comp['nome']}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        print(f"Titolo: {page.title()}")

        testo = page.inner_text("body")
        testo_lower = testo.lower()

        # Cerca header tabella camere
        for kw in ["Tipologia camera", "tipo di camera", "room type", "tipo camera"]:
            if kw.lower() in testo_lower:
                print(f"  ✓ trovato header: '{kw}'")
                idx = testo_lower.find(kw.lower())
                print(f"  Contesto (200 car): {repr(testo[idx:idx+200])}")
                break
        else:
            print("  ✗ nessun header tabella camere trovato")

        # Cerca testo colazione
        for kw in ["colazione inclusa", "prima colazione", "eccezionale colazione",
                   "buona colazione", "solo pernottamento", "b&b"]:
            if kw in testo_lower:
                idx = testo_lower.find(kw)
                print(f"  pensione '{kw}': {repr(testo[idx:idx+60])}")

        # Tutti i prezzi € brevi
        trovati = set()
        for el in page.locator("*").all():
            try:
                t = el.inner_text().strip().split("\n")[0]
                if "€" in t and 2 < len(t) < 25 and t not in trovati:
                    trovati.add(t)
                    print(f"  € → '{t}'")
            except Exception:
                pass
        if not trovati:
            print("  → nessun prezzo trovato")

        # Presenza strutture simili
        if "strutture simili" in testo_lower:
            print("  ⚠ pagina ha 'strutture simili' — hotel non disponibile per queste date")

    browser.close()
