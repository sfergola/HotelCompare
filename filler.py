"""
filler.py — arricchisce il JSON più recente con prezzi storici.

Per ogni hotel × giorno senza prezzo nel run corrente (stato: non_trovato o esaurito),
cerca il prezzo più recente nei run precedenti e aggiunge i campi:
  storico_prezzo  — es. "€ 120*"
  storico_notti   — notti del soggiorno che aveva prodotto quel prezzo
  storico_data    — data YYYY-MM-DD del run che aveva quel prezzo
"""

import json
from datetime import date
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


def _computed_date(path: Path) -> date | None:
    try:
        s = path.stem.split("_computed")[-1]
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def esegui_filler(json_corrente: Path):
    tutti = sorted(
        OUTPUT_DIR.glob("calendar_from*_computed*.json"),
        key=lambda f: _computed_date(f) or date.min,
        reverse=True,
    )

    precedenti = [f for f in tutti if f.resolve() != json_corrente.resolve()]
    if not precedenti:
        print("Filler: nessun run precedente trovato.")
        return

    corrente = json.loads(json_corrente.read_text(encoding="utf-8"))
    calendario = corrente.get("calendario", {})

    # carica tutti i precedenti una volta sola
    storici = [
        (f, json.loads(f.read_text(encoding="utf-8")).get("calendario", {}))
        for f in precedenti
    ]

    modificati = 0
    for nome, giorni_hotel in calendario.items():
        for giorno, entry in giorni_hotel.items():
            if entry.get("prezzo"):
                continue
            for prec_path, prec_cal in storici:
                prec_entry = prec_cal.get(nome, {}).get(giorno)
                if prec_entry and prec_entry.get("prezzo"):
                    d = _computed_date(prec_path)
                    entry["storico_prezzo"] = prec_entry["prezzo"]
                    entry["storico_notti"]  = prec_entry.get("notti", 1)
                    entry["storico_data"]   = str(d) if d else "?"
                    modificati += 1
                    break

    if modificati:
        corrente["calendario"] = calendario
        tmp = json_corrente.with_suffix(".tmp")
        tmp.write_text(json.dumps(corrente, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(json_corrente)
        print(f"Filler: {modificati} date arricchite con storico → {json_corrente.name}")
    else:
        print("Filler: nessun dato storico trovato.")


if __name__ == "__main__":
    files = sorted(
        OUTPUT_DIR.glob("calendar_from*_computed*.json"),
        key=lambda f: _computed_date(f) or date.min,
        reverse=True,
    )
    if files:
        esegui_filler(files[0])
    else:
        print("Nessun file computed trovato.")
