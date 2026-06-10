"""
filler.py — costruisce il calendario unificato da tutti i run storici.

Logica:
  1. Legge tutti i file calendar_from*_computed*.json, dal più nuovo al più vecchio.
  2. Per ogni hotel × giorno, usa il prezzo più recente disponibile.
  3. Se l'entry più recente non ha prezzo ma un run precedente ce l'ha,
     aggiunge storico_prezzo / storico_notti / storico_data.
  4. Ogni entry con prezzo ottiene data_vista = data del run che l'ha prodotta.
  5. Salva il risultato in output/calendar_merged.json.
  6. File che non contribuiscono nulla vengono segnalati (non eliminati).

Output:
  output/calendar_merged.json — calendario completo, usato da app.py
"""

import json
from datetime import date
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


def _iso_data(dv: str) -> str:
    """Normalizza '20260526' → '2026-05-26'. I formati già ISO passano invariati."""
    if len(dv) == 8 and dv.isdigit():
        return f"{dv[:4]}-{dv[4:6]}-{dv[6:8]}"
    return dv


def _computed_date(path: Path) -> date | None:
    try:
        s = path.stem.split("_computed")[-1]
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def _sorted_files() -> list[Path]:
    return sorted(
        OUTPUT_DIR.glob("calendar_from*_computed*.json"),
        key=lambda f: _computed_date(f) or date.min,
        reverse=True,
    )


def _build_merged() -> dict:
    """
    Merge di tutti i run in un unico calendario, con i prezzi più recenti prioritari.
    Ogni entry ottiene data_vista (prezzo) o storico_* (entry senza prezzo).
    """
    files = _sorted_files()
    if not files:
        return {}

    merged: dict[str, dict[str, dict]] = {}

    for f in files:
        run_date     = _computed_date(f)
        run_date_str = str(run_date) if run_date else ""
        try:
            cal = json.loads(f.read_text(encoding="utf-8")).get("calendario", {})
        except Exception:
            print(f"  Filler: impossibile leggere {f.name}, saltato")
            continue

        contributi = 0
        for hotel, giorni in cal.items():
            hotel_m = merged.setdefault(hotel, {})
            for giorno, entry in giorni.items():
                if giorno not in hotel_m:
                    # Prima volta che vediamo questo giorno per questo hotel.
                    # data_vista: preferisce quella scritta dallo scraper (data
                    # reale dello scrape, più precisa del nome file in run
                    # multi-giorno o push parziali), normalizzata in ISO.
                    new_entry = dict(entry)
                    dv = _iso_data(entry.get("data_vista", ""))
                    if dv:
                        new_entry["data_vista"] = dv
                    elif entry.get("prezzo"):
                        new_entry["data_vista"] = run_date_str
                    hotel_m[giorno] = new_entry
                    contributi += 1
                else:
                    existing = hotel_m[giorno]
                    # Se l'entry esistente non ha prezzo e questo run ce l'ha → storico
                    if not existing.get("prezzo") and entry.get("prezzo"):
                        if not existing.get("storico_prezzo"):
                            existing["storico_prezzo"] = entry["prezzo"]
                            existing["storico_notti"]  = entry.get("notti", 1)
                            existing["storico_data"]   = (_iso_data(entry.get("data_vista", ""))
                                                          or run_date_str)
                            contributi += 1

        if contributi == 0:
            print(f"  Filler: {f.name} non contribuisce nulla di nuovo — ignorato")
        else:
            print(f"  Filler: {f.name} → {contributi} entry aggiunte/arricchite")

    return merged


def esegui_filler(_json_corrente=None):
    """
    Costruisce calendar_merged.json da tutti i run disponibili.
    Chiamato da run.py dopo ogni scraping.
    Il parametro _json_corrente è ignorato (backward compat con versione precedente).
    """
    files = _sorted_files()
    if not files:
        print("Filler: nessun run completato trovato.")
        return

    merged = _build_merged()
    if not merged:
        print("Filler: nessun dato da unire.")
        return

    merged_path = OUTPUT_DIR / "calendar_merged.json"
    tmp         = merged_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"calendario": merged}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(merged_path)

    n_hotel  = len(merged)
    n_giorni = sum(len(v) for v in merged.values())
    print(f"Filler: calendario unificato → {merged_path.name} "
          f"({n_hotel} hotel, {n_giorni} entry totali)")


if __name__ == "__main__":
    esegui_filler()
