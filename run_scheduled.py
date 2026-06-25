"""
run_scheduled.py — avvio automatico notturno dello scraping.

Gira ogni 30 minuti via cron. Parte solo se:
- l'ultimo aggiornamento di calendar_merged.json è più vecchio di GIORNI_TRA_RUN giorni
- siamo nella fascia oraria 19:30–09:00 (PC libero)
- non c'è già un run DAVVERO in corso (vedi run_in_corso: un lock stantio da
  spegnimento brutale/crash viene riconosciuto e rimosso → ripresa automatica)

Per avviare fuori orario o con log visivi: usa il pannello (Super → "HotelCompare").
Per avviare un periodo specifico manualmente: usa run.py direttamente.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from git_utils import git_push_calendar

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
LOCK_FILE = OUTPUT_DIR / "run_in_progress.lock"

# in stagione i prezzi si muovono in fretta: 7 giorni di età erano troppi
GIORNI_TRA_RUN = 3


def aggiornamento_necessario() -> bool:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "output/calendar_merged.json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    ts = result.stdout.strip()
    if not ts:
        return True
    return (time.time() - int(ts)) / 86400 >= GIORNI_TRA_RUN


def in_fascia_automatica() -> bool:
    ora = datetime.now().hour + datetime.now().minute / 60
    return ora >= 19.5 or ora < 9.0


def run_in_corso() -> bool:
    """True solo se un nostro run.py è DAVVERO in esecuzione.

    Il lock contiene il PID di run.py. Se il processo è morto (spegnimento brutale,
    crash, stacco corrente) il lock resta "stantio": senza questo controllo bloccava
    per sempre i run successivi, costringendo a rimuoverlo a mano. Qui verifichiamo
    via /proc che il PID esista E sia ancora un run.py (il check sul cmdline evita i
    falsi positivi da PID riciclato dopo un reboot). Se è stantio lo rimuoviamo e
    ritorniamo False: il prossimo giro di cron riparte da solo dai checkpoint."""
    if not LOCK_FILE.exists():
        return False
    try:
        pid = int(LOCK_FILE.read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        if b"run.py" in cmdline:
            return True
    except (ValueError, OSError):
        pass
    LOCK_FILE.unlink(missing_ok=True)  # lock stantio o illeggibile
    return False


def notifica(messaggio: str):
    subprocess.run(["notify-send", "-t", "10000", "HotelCompare", messaggio], check=False)


def main():
    if run_in_corso():
        sys.exit(0)

    if not aggiornamento_necessario():
        sys.exit(0)

    if not in_fascia_automatica():
        sys.exit(0)  # fuori orario: l'utente usa il pannello

    cfg = json.loads((ROOT / "competitors.json").read_text(encoding="utf-8"))
    oggi = date.today()
    state = {
        "data_inizio": str(oggi + timedelta(days=1)),
        "data_fine": cfg.get("stagione_fine", "2026-09-21"),
    }
    (OUTPUT_DIR / "scheduler_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    notifica("Inizio scraping prezzi competitor — non spegnere il PC")

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py")],
        cwd=ROOT,
        start_new_session=True,
    )
    LOCK_FILE.write_text(str(proc.pid))
    try:
        proc.wait()
    finally:
        LOCK_FILE.unlink(missing_ok=True)

    if proc.returncode == 0:
        git_push_calendar(notifica_fn=notifica)
        notifica("Scraping completato e pubblicato.")
    elif proc.returncode not in (-15, -signal.SIGTERM):
        notifica("Scraping fallito. Controlla output/run_scheduled.log.")

    sys.exit(max(proc.returncode, 0))


if __name__ == "__main__":
    main()
