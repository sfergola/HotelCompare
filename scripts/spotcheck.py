"""
spotcheck.py — verifica live ("contract test" manuale) del parser prezzi.

Confronta il prezzo SALVATO in calendar_merged.json con ciò che il parser estrae
ORA da Booking, per un pugno di celle-campione. Salva il testo grezzo di ogni
pagina (output/spotcheck/) per ispezione a mano e dà un verdetto per cella:

  MATCH      live == salvato                      → parser ok, prezzo stabile
  DRIFT      live != salvato (entrambi prezzi)    → probabile cambio prezzo reale
  ⚠ LOST     salvato c'era, live = non_trovato    → POSSIBILE rottura del parser
  SOLD-OUT   salvato c'era, live = esaurito        → plausibile (camere finite)
  ESAURITO   salvato vuoto, live esaurito          → coerente
  NEW        salvato vuoto, live ha prezzo         → cella prima vuota

È una VERIFICA manuale, non un unit test: tocca la rete (Booking). Lanciala ogni
tanto, o quando sospetti che il parser non legga più bene la realtà.

Uso:
    python scripts/spotcheck.py            # mostra le celle-campione (no rete)
    python scripts/spotcheck.py --live     # esegue lo scrape live (~2-4 min)

Le celle-campione si modificano nella lista CAMPIONI qui sotto.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper import scrapa_query, build_url, chiudi_popup, parse_valore, EURO_RE  # noqa: E402

# (hotel, data) — celle che vuoi verificare. Buona regola: hotel sani + date
# varie (vicina/picco/lontana) + un hotel spesso sold-out per testare l'esaurito.
CAMPIONI = [
    ("Hotel Sirio",     "2026-07-04"),
    ("Hotel Capri",     "2026-06-28"),
    ("Hotel Lido Inn",  "2026-08-08"),
    ("Hotel Dei Tigli", "2026-07-15"),
    ("Hotel Mariotti",  "2026-07-15"),
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _carica():
    cal = json.loads((ROOT / "output/calendar_merged.json").read_text())["calendario"]
    cfg = json.loads((ROOT / "competitors.json").read_text())
    urls = {c["nome"]: c.get("booking_url", "") for c in cfg["competitor"] if c.get("booking_url")}
    return cal, cfg, urls


def _verdetto(stored: str | None, live: str | None, stato: str) -> str:
    if stored and live:
        return "MATCH" if parse_valore(stored) == parse_valore(live) else "DRIFT"
    if stored and not live:
        return "SOLD-OUT" if stato == "esaurito" else "⚠ LOST"
    if not stored and live:
        return "NEW"
    return "ESAURITO" if stato == "esaurito" else "EMPTY"


def mostra_candidati(cal, urls):
    print(f"{'HOTEL':22} {'DATA':12} {'SALVATO':16} {'notti':6} {'visto':12} url?")
    for nome, g in CAMPIONI:
        e = cal.get(nome, {}).get(g, {})
        print(f"{nome:22} {g:12} {str(e.get('prezzo')):16} "
              f"{str(e.get('notti')):6} {e.get('data_vista', '-'):12} "
              f"{'ok' if nome in urls else 'MANCA'}")


def live(cal, cfg, urls):
    from playwright.sync_api import sync_playwright

    dump_dir = ROOT / "output" / "spotcheck"
    dump_dir.mkdir(parents=True, exist_ok=True)
    adulti = cfg.get("adulti", 2)
    esiti = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT, locale="it-IT",
                                  viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for nome, g in CAMPIONI:
            if nome not in urls:
                print(f"\n=== {nome} {g}: NESSUN URL, salto ===")
                continue
            e = cal.get(nome, {}).get(g, {})
            stored = e.get("prezzo")
            notti = e.get("notti") or 1
            checkin = date.fromisoformat(g)
            res = scrapa_query(page, urls[nome], checkin, notti, adulti)
            v = _verdetto(stored, res["prezzo"], res["stato"])
            esiti.append((nome, g, v))
            print(f"\n=== {nome}  {g}  ({notti}n) === [{v}]")
            print(f"  salvato:  {stored}  (visto {e.get('data_vista', '-')})")
            print(f"  live:     {res['prezzo']}   [stato: {res['stato']}]")
            # dump del testo grezzo per ispezione a mano
            try:
                url = build_url(urls[nome], checkin, checkin + timedelta(days=notti), adulti)
                page.goto(url, wait_until="networkidle", timeout=40000)
                chiudi_popup(page)
                page.evaluate("window.scrollTo(0,1200)")
                testo = page.inner_text("body")
                safe = "".join(c if c.isalnum() else "_" for c in nome)[:30]
                (dump_dir / f"{safe}_{g}_{notti}n.txt").write_text(testo, encoding="utf-8")
                righe = [r.strip() for r in testo.split("\n")
                         if EURO_RE.search(r) and len(r.strip()) < 40][:6]
                print(f"  righe € grezze: {righe}")
            except Exception as ex:
                print(f"  dump fallito: {ex}")
        browser.close()

    print("\n" + "=" * 50 + "\nRIEPILOGO")
    for nome, g, v in esiti:
        flag = "  <-- DA GUARDARE" if v in ("⚠ LOST", "DRIFT") else ""
        print(f"  [{v:9}] {nome} {g}{flag}")
    if any(v == "⚠ LOST" for _, _, v in esiti):
        print("\n⚠ Almeno una cella LOST: il parser potrebbe non leggere più. Ispeziona il dump.")


if __name__ == "__main__":
    cal, cfg, urls = _carica()
    mostra_candidati(cal, urls)
    if "--live" in sys.argv:
        print("\n" + "=" * 50 + "\nSCRAPE LIVE (~2-4 min, tocca Booking)\n" + "=" * 50)
        live(cal, cfg, urls)
