"""
git_utils.py — operazioni git condivise tra run.py e run_scheduled.py.
"""

import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent


def _branch_corrente() -> str:
    res = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return res.stdout.strip() or "main"


def git_push_calendar(notifica_fn=None) -> bool:
    """
    Committa calendar_merged.json e fa push sul branch corrente.
    Ritorna True se il push va a buon fine, False altrimenti (così il chiamante
    può far fallire il run: una push persa = dati persi in silenzio).
    notifica_fn: callable(messaggio) opzionale per notifiche desktop.
    """
    subprocess.run(["git", "add", "output/calendar_merged.json"], cwd=ROOT, check=False)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode == 0:
        print("Git: nessuna modifica da committare.")
        return True

    oggi_str = date.today().strftime("%d/%m/%Y")
    commit = subprocess.run(
        ["git", "commit", "-m", f"chore: aggiornamento prezzi {oggi_str}"],
        cwd=ROOT, check=False,
    )
    if commit.returncode != 0:
        print("Git: commit fallito.")
        if notifica_fn:
            notifica_fn("Commit fallito. Controlla il terminale.")
        return False

    branch = _branch_corrente()
    # un run dura ore: il remoto può essere avanzato nel frattempo (un altro
    # commit sul branch). Rebase del nostro commit — che tocca solo
    # calendar_merged.json — sopra le novità, poi push. Retry per i push concorrenti.
    for _ in range(3):
        subprocess.run(["git", "pull", "--rebase", "origin", branch], cwd=ROOT, check=False)
        push = subprocess.run(["git", "push", "origin", branch], cwd=ROOT, check=False)
        if push.returncode == 0:
            print(f"Git: push completato su '{branch}' → Streamlit aggiornato.")
            return True

    print("Git: push fallito dopo 3 tentativi.")
    if notifica_fn:
        notifica_fn("Push fallito. Controlla la connessione di rete.")
    return False
