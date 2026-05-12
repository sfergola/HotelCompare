"""
run_scheduled.py — wrapper per esecuzione automatica settimanale.

Gira ogni 30 minuti via cron. Parte solo se l'ultimo aggiornamento
di calendar_merged.json è più vecchio di 7 giorni.

Comportamento in base all'ora:
- 19:30–09:00 → parte in automatico (fascia notturna, PC libero)
- 09:00–19:30 → mostra popup: l'utente decide se avviare ora o rimandare

Per avviare manualmente un periodo specifico: usa run.py direttamente.
"""

import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from git_utils import git_push_calendar

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
LOCK_FILE = OUTPUT_DIR / "run_in_progress.lock"


def aggiornamento_necessario() -> bool:
    """Controlla se calendar_merged.json non è stato aggiornato negli ultimi 7 giorni."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "output/calendar_merged.json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    ts = result.stdout.strip()
    if not ts:
        return True  # mai committato → va aggiornato
    giorni_passati = (time.time() - int(ts)) / 86400
    return giorni_passati >= 7


def in_fascia_automatica() -> bool:
    """Ritorna True se siamo nella finestra 19:30–09:00 (il PC di solito è libero)."""
    ora = datetime.now().hour + datetime.now().minute / 60
    return ora >= 19.5 or ora < 9.0


def chiedi_utente() -> bool:
    """
    Mostra popup zenity con due opzioni.
    Ritorna True se l'utente clicca 'Avvia ora'.
    Auto-chiude dopo 60s (= 'Più tardi').
    """
    result = subprocess.run(
        [
            "zenity", "--question",
            "--title=HotelCompare — aggiornamento prezzi",
            "--text=Sono passati più di 7 giorni dall'ultimo aggiornamento.\nVuoi avviare lo scraping adesso?",
            "--ok-label=Avvia ora",
            "--cancel-label=Più tardi",
            "--timeout=60",
        ],
        check=False,
    )
    return result.returncode == 0


def notifica(messaggio: str):
    subprocess.run(["notify-send", "-t", "10000", "HotelCompare", messaggio], check=False)


def avvia():
    cfg_path = ROOT / "competitors.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    oggi = date.today()
    state = {
        "data_inizio": str(oggi + timedelta(days=1)),
        "data_fine":   cfg.get("stagione_fine", "2026-09-21"),
    }
    state_path = OUTPUT_DIR / "scheduler_state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    notifica("Inizio scraping prezzi competitor — non spegnere il PC")

    LOCK_FILE.touch()
    try:
        result = subprocess.run([sys.executable, str(ROOT / "run.py")], cwd=ROOT)
    finally:
        LOCK_FILE.unlink(missing_ok=True)

    if result.returncode == 0:
        git_push_calendar(notifica_fn=notifica)
        notifica("Scraping completato e pubblicato.")
    else:
        notifica("Scraping fallito. Controlla il terminale.")

    sys.exit(result.returncode)


def main():
    if LOCK_FILE.exists():
        print("Run già in corso. Skip.")
        sys.exit(0)

    if not aggiornamento_necessario():
        sys.exit(0)

    if in_fascia_automatica():
        avvia()
    else:
        if chiedi_utente():
            avvia()


if __name__ == "__main__":
    main()
