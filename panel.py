"""
panel.py — pannello di controllo HotelCompare.

Avvia dal launcher GNOME (tasto Super → "HotelCompare").
Mostra stato ultimo aggiornamento, log in tempo reale, bottoni Avvia/Stop.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import scrolledtext

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
LOCK_FILE = OUTPUT_DIR / "run_in_progress.lock"
PYTHON = Path(sys.executable)


def _ultimo_aggiornamento() -> tuple[str, int]:
    """Ritorna (data_formattata, giorni_fa) dell'ultimo commit di calendar_merged.json."""
    res = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "output/calendar_merged.json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    ts_str = res.stdout.strip()
    if not ts_str:
        return "mai", 9999
    ts = int(ts_str)
    data = datetime.fromtimestamp(ts).strftime("%d/%m/%Y")
    giorni = int((time.time() - ts) / 86400)
    return data, giorni


def _ha_checkpoint() -> bool:
    return any(OUTPUT_DIR.glob("*_inprogress.json"))


def _processo_attivo() -> tuple[bool, int | None]:
    """Controlla se c'è un run in corso leggendo il PID dal lock file."""
    if not LOCK_FILE.exists():
        return False, None
    try:
        pid = int(LOCK_FILE.read_text().strip())
        os.kill(pid, 0)  # solleva ProcessLookupError se il processo non esiste
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        LOCK_FILE.unlink(missing_ok=True)
        return False, None


class Panel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HotelCompare")
        self.root.geometry("860x520")
        self.root.resizable(True, True)
        self.proc: subprocess.Popen | None = None
        self._log_esterno_annunciato = False
        self._build_ui()
        self._aggiorna_stato()

    def _build_ui(self):
        fr_stato = tk.Frame(self.root, padx=14, pady=10)
        fr_stato.pack(fill=tk.X)
        tk.Label(fr_stato, text="Stato:", font=("", 10, "bold")).pack(side=tk.LEFT)
        self.lbl_stato = tk.Label(fr_stato, text="…", font=("", 10))
        self.lbl_stato.pack(side=tk.LEFT, padx=8)

        fr_btn = tk.Frame(self.root, padx=14, pady=2)
        fr_btn.pack(fill=tk.X)
        self.btn_avvia = tk.Button(fr_btn, text="Avvia", width=14, command=self._avvia)
        self.btn_avvia.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = tk.Button(
            fr_btn, text="Stop", width=14, command=self._stop, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT)

        fr_log = tk.Frame(self.root, padx=14, pady=6)
        fr_log.pack(fill=tk.BOTH, expand=True)
        tk.Label(fr_log, text="Log", font=("", 9, "bold"), anchor="w").pack(fill=tk.X)
        self.txt_log = scrolledtext.ScrolledText(
            fr_log,
            height=22,
            font=("Monospace", 9),
            state=tk.DISABLED,
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def _log(self, riga: str):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, riga)
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _aggiorna_stato(self):
        attivo, _ = _processo_attivo()

        if attivo:
            self.lbl_stato.config(text="In esecuzione…", fg="#e5a000")
            self.btn_avvia.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            # Run partito esternamente (cron notturno): avvisiamo una volta sola
            if self.proc is None and not self._log_esterno_annunciato:
                self._log("[scraping in corso — avviato automaticamente]\n")
                self._log("[log disponibili in output/run_scheduled.log]\n")
                self._log_esterno_annunciato = True
        else:
            data, giorni = _ultimo_aggiornamento()
            checkpoint = _ha_checkpoint()

            if giorni >= 7:
                self.lbl_stato.config(
                    text=f"Da aggiornare  ({data} · {giorni} giorni fa)", fg="#cc3333"
                )
            else:
                self.lbl_stato.config(
                    text=f"Aggiornato  ({data} · {giorni} giorni fa)", fg="#2d8a2d"
                )

            self.btn_avvia.config(
                text="Riprendi" if checkpoint else "Avvia", state=tk.NORMAL
            )
            self.btn_stop.config(state=tk.DISABLED)

            if self.proc is not None:
                self.proc = None
                self._log_esterno_annunciato = False

        self.root.after(2000, self._aggiorna_stato)

    def _avvia(self):
        cfg = json.loads((ROOT / "competitors.json").read_text(encoding="utf-8"))
        oggi = date.today()
        state = {
            "data_inizio": str(oggi + timedelta(days=1)),
            "data_fine": cfg.get("stagione_fine", "2026-09-21"),
        }
        (OUTPUT_DIR / "scheduler_state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self.proc = subprocess.Popen(
            [str(PYTHON), str(ROOT / "run.py")],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,  # processo indipendente → killpg funziona
        )
        LOCK_FILE.write_text(str(self.proc.pid))

        self.btn_avvia.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_stato.config(text="In esecuzione…", fg="#e5a000")

        threading.Thread(target=self._leggi_output, daemon=True).start()

    def _leggi_output(self):
        for line in self.proc.stdout:
            self.root.after(0, self._log, line)

        returncode = self.proc.wait()
        LOCK_FILE.unlink(missing_ok=True)

        if returncode == 0:
            from git_utils import git_push_calendar
            git_push_calendar()
            self.root.after(0, self._log, "\n✓ Completato e pubblicato su GitHub.\n")
        elif returncode in (-signal.SIGTERM, -15):
            self.root.after(0, self._log, "\n[Fermato — checkpoint salvati, puoi riprendere]\n")
        else:
            self.root.after(0, self._log, f"\n✗ Fallito (codice {returncode}).\n")

    def _stop(self):
        attivo, pid = _processo_attivo()
        if not attivo or pid is None:
            return
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        LOCK_FILE.unlink(missing_ok=True)
        self._log("\n[Stop richiesto — i dati già scrappati sono al sicuro nei checkpoint]\n")
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_avvia.config(state=tk.NORMAL)


def main():
    root = tk.Tk()
    Panel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
