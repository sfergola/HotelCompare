"""
run.py — entry point del calendario prezzi competitor.

Uso:
    python run.py

Fasi:
    1. Carica config da competitors.json
    2. Risolve URL Booking per hotel senza URL (browser dedicato)
    3. Scrapa ogni hotel in parallelo (max_workers browser separati)
    4. Unisce i file parziali in un unico calendario JSON
    5. Esegue filler (merge storico + data_vista)
    6. Genera CSV e TXT
    7. Commit e push di calendar_merged.json
"""

import json
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper import risolvi_urls
from algorithm import scrapa_hotel_worker, giorno_range, safe_nome
from report import genera_csv, genera_report_testo


CONFIG_PATH = Path(__file__).parent / "competitors.json"
OUTPUT_DIR  = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def carica_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def salva_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _merge_partials(urls: dict, from_str: str, to_str: str,
                    oggi_str: str) -> dict:
    """Unisce i file partial per-hotel nel calendario finale."""
    calendario = {}
    for nome in urls:
        safe      = safe_nome(nome)
        done_path = OUTPUT_DIR / f"partial_{safe}_from{from_str}_to{to_str}_computed{oggi_str}.json"
        if done_path.exists():
            d         = json.loads(done_path.read_text(encoding="utf-8"))
            cal_hotel = d.get("calendario", {}).get(nome, {})
            calendario[nome] = cal_hotel
        else:
            print(f"  ⚠ {nome}: file partial non trovato, hotel escluso dal calendario")
    return calendario


def main():
    cfg         = carica_config()
    data_fine   = date.fromisoformat(cfg["data_fine"])
    adulti      = cfg.get("adulti", 2)
    max_workers = cfg.get("max_workers", 3)
    oggi        = date.today()
    data_inizio = date.fromisoformat(cfg["data_inizio"]) if "data_inizio" in cfg else oggi

    giorni    = list(giorno_range(data_inizio, data_fine))
    from_str  = str(data_inizio).replace("-", "")
    to_str    = str(data_fine).replace("-", "")
    oggi_str  = str(oggi).replace("-", "")

    print(f"HotelCompare — {len(cfg['competitor'])} competitor, "
          f"{len(giorni)} giorni ({data_inizio} → {data_fine}), "
          f"max_workers={max_workers}\n")

    # ── Fase 1: risoluzione URL (browser singolo) ───────────────────────────
    print("=== Fase 1: risoluzione URL ===")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(
            user_agent=USER_AGENT, locale="it-IT",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        urls, aggiornato = risolvi_urls(page, cfg)
        browser.close()

    if aggiornato:
        salva_config(cfg)
        print("  ✓ competitors.json aggiornato.\n")

    manuali = {c["nome"]: c["nota"] for c in cfg["competitor"] if "nota" in c}

    if not urls:
        print("Nessun URL trovato.")
        return

    # ── Fase 2: scraping parallelo ──────────────────────────────────────────
    print(f"=== Fase 2: scraping parallelo ({len(urls)} hotel, max {max_workers} alla volta) ===\n")

    args_list = [
        (nome, url,
         str(data_inizio), str(data_fine), adulti,
         str(OUTPUT_DIR), from_str, to_str, oggi_str,
         USER_AGENT)
        for nome, url in urls.items()
    ]

    falliti = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scrapa_hotel_worker, args): args[0]
                   for args in args_list}
        for future in as_completed(futures):
            nome = futures[future]
            try:
                nome_ret, _ = future.result()
                print(f"✓ {nome_ret} completato")
            except Exception as exc:
                print(f"✗ {nome} fallito: {exc}")
                falliti.append(nome)

    if falliti:
        print(f"\n⚠ Hotel non completati: {', '.join(falliti)}")

    # ── Fase 3: unione partial → calendario finale ──────────────────────────
    print("\n=== Fase 3: unione calendari ===")
    calendario = _merge_partials(urls, from_str, to_str, oggi_str)

    if not calendario:
        print("Nessun dato disponibile — interrompo.")
        return

    stem_done = f"calendar_from{from_str}_to{to_str}_computed{oggi_str}"
    json_done = OUTPUT_DIR / f"{stem_done}.json"
    csv_path  = OUTPUT_DIR / f"{stem_done}.csv"
    txt_path  = OUTPUT_DIR / f"{stem_done}.txt"

    meta = {
        "data_inizio": str(data_inizio),
        "data_fine":   str(data_fine),
        "adulti":      adulti,
    }
    tmp = json_done.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"meta": meta, "calendario": calendario}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(json_done)
    print(f"  ✓ {json_done.name}")

    # ── Fase 4: filler (merge storico + data_vista) ─────────────────────────
    from filler import esegui_filler
    esegui_filler()

    # ── Fase 5: report ──────────────────────────────────────────────────────
    tutti_nomi  = list(urls.keys()) + list(manuali.keys())
    giorni_str  = [str(g) for g in giorno_range(data_inizio, data_fine)]
    riferimento = next((c["nome"] for c in cfg["competitor"] if c.get("riferimento")), "")

    csv_path.write_text(
        genera_csv(calendario, tutti_nomi, manuali, giorni_str, riferimento),
        encoding="utf-8")
    txt_path.write_text(
        genera_report_testo(calendario, tutti_nomi, manuali, giorni_str, riferimento),
        encoding="utf-8")

    print(f"\nDone.\n  JSON  : {json_done}\n  CSV   : {csv_path}\n  Testo : {txt_path}\n")
    print(genera_report_testo(calendario, tutti_nomi, manuali, giorni_str[:31], riferimento))

    _git_push()


def _git_push():
    root = Path(__file__).parent
    subprocess.run(["git", "add", "output/calendar_merged.json"], cwd=root, check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root)
    if diff.returncode == 0:
        print("Git: nessuna modifica da committare.")
        return
    oggi_str = date.today().strftime("%d/%m/%Y")
    commit = subprocess.run(
        ["git", "commit", "-m", f"chore: aggiornamento prezzi {oggi_str}"],
        cwd=root, check=False,
    )
    if commit.returncode != 0:
        print("Git: commit fallito.")
        return
    push = subprocess.run(["git", "push", "origin", "main"], cwd=root, check=False)
    if push.returncode != 0:
        print("Git: push fallito — controlla la connessione.")
    else:
        print("Git: push completato → Streamlit aggiornato.")


if __name__ == "__main__":
    main()
