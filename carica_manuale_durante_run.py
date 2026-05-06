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
import subprocess
from datetime import date
from pathlib import Path

from algorithm import safe_nome
from filler import esegui_filler


CONFIG_PATH = Path(__file__).parent / "competitors.json"
OUTPUT_DIR  = Path(__file__).parent / "output"


def main():
    cfg         = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data_inizio = date.fromisoformat(cfg["data_inizio"])
    data_fine   = date.fromisoformat(cfg["data_fine"])
    oggi        = date.today()
    from_str    = str(data_inizio).replace("-", "")
    to_str      = str(data_fine).replace("-", "")
    oggi_str    = str(oggi).replace("-", "")

    print(f"Range run: {data_inizio} → {data_fine}\n")

    urls = {
        c["nome"]: c.get("booking_url")
        for c in cfg["competitor"]
        if c.get("booking_url")
    }

    calendario = {}

    for nome in urls:
        safe      = safe_nome(nome)
        computed  = OUTPUT_DIR / f"partial_{safe}_from{from_str}_to{to_str}_computed{oggi_str}.json"
        inprogress = OUTPUT_DIR / f"partial_{safe}_from{from_str}_to{to_str}_inprogress.json"

        if computed.exists():
            d   = json.loads(computed.read_text(encoding="utf-8"))
            cal = d.get("calendario", {}).get(nome, {})
            calendario[nome] = cal
            print(f"  ✓ {nome}: {len(cal)} giorni (completo)")
        elif inprogress.exists():
            d   = json.loads(inprogress.read_text(encoding="utf-8"))
            cal = d.get("calendario", {}).get(nome, {})
            if cal:
                calendario[nome] = cal
                print(f"  ~ {nome}: {len(cal)} giorni (in corso)")
            else:
                print(f"  - {nome}: ancora da iniziare")
        else:
            print(f"  - {nome}: ancora da iniziare")

    if not calendario:
        print("\nNessun dato disponibile — run non ancora avviato?")
        return

    meta    = {"data_inizio": str(data_inizio), "data_fine": str(data_fine), "adulti": cfg.get("adulti", 2)}
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
