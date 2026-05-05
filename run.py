"""
run.py — entry point del calendario prezzi competitor.

Uso:
    python run.py

Fasi:
    1. Carica config da competitors.json
    2. Risolve URL Booking per hotel senza URL
    3. Scrapa prezzi giorno per giorno (con checkpoint)
    4. Genera CSV e TXT
"""

import json
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper import risolvi_urls
from algorithm import scrapa_calendario, giorno_range
from report import genera_csv, genera_report_testo


CONFIG_PATH = Path(__file__).parent / "competitors.json"
OUTPUT_DIR  = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def carica_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def salva_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def main():
    cfg         = carica_config()
    data_fine   = date.fromisoformat(cfg["data_fine"])
    adulti      = cfg.get("adulti", 2)
    oggi        = date.today()
    data_inizio = date.fromisoformat(cfg["data_inizio"]) if "data_inizio" in cfg else oggi

    giorni = list(giorno_range(data_inizio, data_fine))
    print(f"HotelCompare calendario — {len(cfg['competitor'])} competitor, "
          f"{len(giorni)} giorni ({data_inizio} → {data_fine})\n")

    from_str  = str(data_inizio).replace("-", "")
    to_str    = str(data_fine).replace("-", "")
    oggi_str  = str(oggi).replace("-", "")
    stem_prog = f"calendar_from{from_str}_to{to_str}_inprogress"
    stem_done = f"calendar_from{from_str}_to{to_str}_computed{oggi_str}"

    json_prog = OUTPUT_DIR / f"{stem_prog}.json"
    csv_path  = OUTPUT_DIR / f"{stem_done}.csv"
    txt_path  = OUTPUT_DIR / f"{stem_done}.txt"
    json_done = OUTPUT_DIR / f"{stem_done}.json"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            locale="it-IT",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        try:
            print("=== Fase 1: risoluzione URL ===")
            urls, aggiornato = risolvi_urls(page, cfg)
            if aggiornato:
                salva_config(cfg)
                print("  ✓ competitors.json aggiornato.\n")

            manuali = {c["nome"]: c["nota"] for c in cfg["competitor"] if "nota" in c}

            if not urls:
                print("Nessun URL trovato.")
                return

            totale_query_max = len(giorni) * len(urls) * 7
            print(f"=== Fase 2: scraping (max {totale_query_max} query) ===\n")

            calendario = scrapa_calendario(
                page, urls, data_inizio, data_fine, adulti, json_prog
            )

        finally:
            browser.close()

    # Rinomina il file in-progress → file finale
    if json_prog.exists():
        json_prog.replace(json_done)

    from filler import esegui_filler
    esegui_filler(json_done)

    tutti_nomi  = list(urls.keys()) + list(manuali.keys())
    giorni_str  = [str(g) for g in giorno_range(data_inizio, data_fine)]

    csv_path.write_text(
        genera_csv(calendario, tutti_nomi, manuali, giorni_str), encoding="utf-8")
    txt_path.write_text(
        genera_report_testo(calendario, tutti_nomi, manuali, giorni_str), encoding="utf-8")

    print(f"\nDone.\n  JSON : {json_done}\n  CSV  : {csv_path}\n  Testo: {txt_path}\n")
    print(genera_report_testo(calendario, tutti_nomi, manuali, giorni_str[:31]))


if __name__ == "__main__":
    main()
