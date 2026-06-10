"""
carica_manuale_durante_run.py — pubblica i dati parziali mentre run.py è ancora in corso.

Uso:
    python carica_manuale_durante_run.py

Cosa fa:
    1. Legge competitors.json per sapere il range date del run corrente
    2. Raccoglie i file partial già completati (_computed) e quelli ancora in corso (_inprogress)
    3. Costruisce un calendario parziale e lo salva come file computed
    4. Esegue filler per aggiornare calendar_merged.json
    5. Commit + push

Sicuro da eseguire mentre run.py gira: legge i file partial senza modificarli.
Il run al termine sovrascriverà il calendario con i dati completi e farà push di nuovo.
"""

import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

from algorithm import safe_nome
from filler import esegui_filler


CONFIG_PATH = Path(__file__).parent / "competitors.json"
OUTPUT_DIR  = Path(__file__).parent / "output"

# run.py calcola le date a runtime (oggi+1 o scheduler_state.json), quindi il
# range nel nome file non è ricostruibile da competitors.json: si cerca per
# glob il partial più recente di ogni hotel, ignorando i file di run vecchi.
MAX_ETA_PARTIAL_ORE = 48


def _trova_partial(safe: str) -> Path | None:
    candidati = sorted(
        OUTPUT_DIR.glob(f"partial_{safe}_from*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidati:
        if time.time() - p.stat().st_mtime <= MAX_ETA_PARTIAL_ORE * 3600:
            return p
    return None


def main():
    cfg      = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    oggi     = date.today()
    oggi_str = str(oggi).replace("-", "")

    urls = {
        c["nome"]: c.get("booking_url")
        for c in cfg["competitor"]
        if c.get("booking_url")
    }

    calendario = {}
    from_str = to_str = None

    for nome in urls:
        safe = safe_nome(nome)
        path = _trova_partial(safe)

        if path is None:
            print(f"  - {nome}: nessun partial recente")
            continue

        m = re.search(r"_from(\d{8})_to(\d{8})_", path.name)
        if m and from_str is None:
            from_str, to_str = m.group(1), m.group(2)

        d   = json.loads(path.read_text(encoding="utf-8"))
        cal = d.get("calendario", {}).get(nome, {})
        if not cal:
            print(f"  - {nome}: ancora da iniziare")
            continue
        calendario[nome] = cal
        stato = "completo" if "_computed" in path.name else "in corso"
        print(f"  {'✓' if stato == 'completo' else '~'} {nome}: {len(cal)} giorni ({stato})")

    if not calendario or not from_str:
        print("\nNessun dato disponibile — run non ancora avviato?")
        return

    def _iso(s: str) -> str:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

    print(f"\nRange run rilevato: {_iso(from_str)} → {_iso(to_str)}")

    meta    = {"data_inizio": _iso(from_str), "data_fine": _iso(to_str), "adulti": cfg.get("adulti", 2)}
    outfile = OUTPUT_DIR / f"calendar_from{from_str}_to{to_str}_computed{oggi_str}.json"
    tmp     = outfile.with_suffix(".tmp")
    tmp.write_text(json.dumps({"meta": meta, "calendario": calendario}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(outfile)
    print(f"\nCalendario parziale scritto: {outfile.name}")

    print("\nFiller...")
    esegui_filler()

    _git_push(oggi)


def _git_push(oggi: date):
    root     = Path(__file__).parent
    oggi_fmt = oggi.strftime("%d/%m/%Y")

    subprocess.run(["git", "add", "output/calendar_merged.json"], cwd=root, check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root)
    if diff.returncode == 0:
        print("Git: nessuna modifica da committare.")
        return

    commit = subprocess.run(
        ["git", "commit", "-m", f"chore: aggiornamento parziale prezzi {oggi_fmt}"],
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
