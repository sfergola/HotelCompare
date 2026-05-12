"""
run_scheduled.py — wrapper per esecuzione automatica settimanale (solo locale).

Runna solo se:
- Oggi è lunedì, martedì o mercoledì (weekday 0-2)
- Non esiste già un file calendar_*_computed{questa_settimana}.json

Per esecuzione manuale o aggiornamento di un singolo periodo usa run.py direttamente.
GitHub Actions è disabilitato — tutto avviene in locale via cron @reboot.
"""

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from git_utils import git_push_calendar

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"


def inizio_settimana() -> date:
    oggi = date.today()
    return oggi - timedelta(days=oggi.weekday())


def gia_fatto_questa_settimana() -> bool:
    inizio = inizio_settimana()
    for f in OUTPUT_DIR.glob("calendar_from*_computed*.json"):
        try:
            computed_str = f.stem.split("_computed")[-1]
            computed = date(int(computed_str[:4]), int(computed_str[4:6]), int(computed_str[6:8]))
            if computed >= inizio:
                return True
        except (ValueError, IndexError):
            continue
    return False


def notifica(messaggio: str):
    subprocess.run(["notify-send", "-t", "10000", "HotelCompare", messaggio], check=False)


def main():
    oggi = date.today()

    if oggi.weekday() > 2:
        sys.exit(0)

    if gia_fatto_questa_settimana():
        print("Run già completato questa settimana. Skip.")
        sys.exit(0)

    # Scrive le date di run in scheduler_state.json invece di modificare competitors.json.
    # run.py legge da qui se il file esiste, e lo cancella dopo l'uso.
    cfg_path = ROOT / "competitors.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    state = {
        "data_inizio": str(oggi + timedelta(days=1)),
        "data_fine":   cfg.get("stagione_fine", "2026-09-21"),
    }
    state_path = OUTPUT_DIR / "scheduler_state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    notifica("Inizio scraping prezzi competitor — non spegnere il PC")

    result = subprocess.run([sys.executable, str(ROOT / "run.py")], cwd=ROOT)

    if result.returncode == 0:
        git_push_calendar(notifica_fn=notifica)
        notifica("Scraping completato e pubblicato. Puoi spegnere il PC.")
    else:
        notifica("Scraping fallito. Controlla il terminale.")

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
