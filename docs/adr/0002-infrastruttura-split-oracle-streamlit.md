# Infrastruttura split: Oracle Cloud (scraping) + Streamlit Cloud (web app)

Lo scraping gira su Oracle Cloud Free Tier (VM ARM, Always Free), la web app resta su Streamlit Community Cloud. I due componenti comunicano solo tramite GitHub: il scraper committa `calendar_merged.json`, Streamlit lo legge dal repo.

## Considered Options

**Tutto sul PC personale**: situazione attuale. Funziona ma richiede che il PC sia acceso, scalda, occupa risorse durante il lavoro.

**GitHub Actions**: gratuito illimitato per repo pubblici, ma i runner hanno IP da range Microsoft/Azure — bloccati da Booking.com quasi certamente.

**VPS a pagamento (DigitalOcean, Hetzner)**: costo mensile di mercato, IP migliore, ma inutile finché Oracle Free copre il bisogno.

**Oracle Cloud Free Tier scelto**: VM ARM 4 core / 24GB RAM, gratuita a tempo indeterminato. Streamlit Cloud resta separato perché è già configurato, gratuito, e non ha senso duplicarlo.

## Consequences

- Il cron su Oracle Cloud sostituisce `@reboot` in `run_scheduled.py` — la guard Lun/Mar/Mer rimane nel codice. Se il cron salta (VM in manutenzione), non c'è alerting — il calendar resta fermo fino al run successivo.
- I file `output/partial_*` sono locali alla VM. Se la VM si riavvia durante un run, i partial si perdono e il run successivo riparte da zero per quegli hotel. Accettabile per ora — il checkpoint evita corruzioni (Issue #1).
- Autenticazione GitHub dalla VM: SSH key dedicata come Deploy key con write access. Setup:
  1. `ssh-keygen -t ed25519 -f ~/.ssh/id_hotelcompare` sulla VM
  2. Aggiungere `~/.ssh/id_hotelcompare.pub` in GitHub → repo Settings → Deploy keys (write access)
  3. Configurare `~/.ssh/config` con `IdentityFile ~/.ssh/id_hotelcompare` per il remote
  4. Se la VM viene persa: rigenerare la chiave e aggiornare il Deploy key su GitHub
- Nessuna credenziale in `.env` richiesta — lo scraper naviga Booking in modo anonimo.
- Oracle ha revocato VM inattive in passato — fare login mensile alla console per evitare reclaim.
- IP Oracle non risulta nella blocklist di Booking.com alla data della decisione — da verificare al primo run.
