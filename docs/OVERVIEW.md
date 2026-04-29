<!--
  Generato da /explain_project
  Ultimo aggiornamento: 2026-04-29
  Commit di riferimento: ce99f2c
  Aggiornato da audit 2026-04-29
-->

## VISIONE — A COSA SERVE QUESTO PROGETTO

HotelCompare permette a Hotel Nuovo Tirreno (Lido di Camaiore) di monitorare i prezzi dei competitor su Booking.com senza doverli cercare a mano ogni settimana. Produce un report con hotel per riga e date per colonna — leggibile come un gestionale — con il prezzo di camera matrimoniale B&B per ogni sabato della stagione.

---

## OBIETTIVO FINALE

Script eseguibile ogni lunedì mattina (manuale o schedulato) che genera in ~5 minuti un CSV e un report testo con i prezzi aggiornati di tutti i competitor, pronto da aprire in Excel o leggere nel terminale.

---

## PUNTO DI PARTENZA (stato attuale)

**Cosa c'è già:**
- Scraper funzionante per 12 hotel su Booking.com + 2 in verifica manuale
- 3 tipi di query per settimana: Sab→Sab (7n), Lun→Sab (5n), Sab→Lun (2n)
- Dual parser: gestisce sia il layout tabella che il layout card di Booking.com
- Marker camera: standard / economy `#` / singola `S` / B&B `*`
- Divisione prezzo settimanale → notte con sanity check (scarta valori < €25)
- Output CSV `hotel × date` + report testo con legenda
- Periodo configurabile via `data_inizio` / `data_fine` in `competitors.json`

**Cosa manca:**
- Run programmato automatico (si lancia a mano)
- Hotel Verbena e Alba sul Mare non sono su Booking → verifica manuale

---

## CHI USA L'APP E COME

**Utente:** il proprietario / receptionist dell'hotel.

Flusso tipico:
1. Apre il terminale, attiva il venv, lancia `python compare_booking.py`
2. Aspetta ~5 min (se periodo breve) o ~25 min (stagione completa)
3. Apre `output/report_YYYYMMDD.csv` in Excel oppure legge il `.txt` nel terminale
4. Confronta la riga MEDIA con il proprio listino e aggiusta se necessario

---

## ARCHITETTURA — COM'È FATTO IL SISTEMA

```
competitors.json
    ↓
compare_booking.py: main()
    ├── risolvi_urls()          cerca URL su Booking se mancante, salva nel JSON
    └── per ogni sabato × hotel:
            scrapa_notte()
                ├── page.goto(booking_url?checkin=...&checkout=...7gg)
                └── estrai_prezzo()
                        ├── Parser 1: layout tabella ("Tipologia camera")
                        ├── Parser 2: layout card ("N° max persone")
                        └── Fallback: primo €  nella sezione principale
    ↓
genera_csv() + genera_report_testo()
    ↓
output/report_YYYYMMDD.csv + .txt
```

**Decisione chiave:** query da 7 notti invece di 1 notte. Gli hotel costieri italiani applicano soggiorno minimo settimanale in alta stagione — con query 1-notte restituiscono "non disponibile". Il prezzo settimanale viene diviso per 7 per ottenere il notte.

**Dual parser:** Booking.com usa due layout diversi per la pagina hotel. Il parser corretto viene selezionato automaticamente in base al marker presente nella pagina.

---

## STACK TECNICO

| Componente | Tecnologia | Perché |
|---|---|---|
| Scraping | Playwright + Chromium (headless) | Booking.com usa JavaScript per renderizzare i prezzi |
| Config | JSON | Modificabile a mano senza codice |
| Output | CSV + testo | Compatibile con Excel e leggibile nel terminale |
| Runtime | Python 3.10+ | Standard, venv incluso |

Dipendenze: `playwright`, nient'altro.

---

## CONTESTO COMPETITOR

| Hotel | Stato | Note |
|---|---|---|
| Hotel Lido Inn | ✅ prezzi confermati | Layout tabella, matrimoniale B&B rilevato |
| Hotel Sirio | ✅ prezzi confermati | Layout card |
| Hotel Capri | ✅ prezzi confermati | Layout card, qualche lacuna in bassa stagione |
| Hotel Dei Tigli | ⚠️ solo bassa stagione | In alta stagione non disponibile su Booking |
| Hotel Mariotti | ⚠️ discontinuo | Disponibile luglio-agosto |
| Hotel La Vela | ✅ alta stagione | Fix ~€4 applicato (bassa stagione) |
| Hotel Florentia | ✅ aggiunto | URL confermato |
| Hotel Luca | ✅ aggiunto | URL confermato |
| Hotel Lungomare | ✅ aggiunto | URL confermato |
| Hotel Perla del Mare | ✅ aggiunto | URL confermato |
| Hotel Milani | ✅ aggiunto | URL confermato |
| Hotel Sylvia | ✅ aggiunto | URL confermato |
| Hotel Verbena | ❌ non su Booking | Verifica manuale su hotelverbena.it |
| Hotel Alba sul Mare | ❌ non su Booking | Verifica manuale su hotelalbasulmare.it |

---

## COME CONTRIBUIRE — GUIDA PRATICA

```bash
git clone git@github.com:sfergola/HotelCompare.git
cd HotelCompare
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Test rapido su una data:
python test_one_night.py

# Run completo stagione:
python compare_booking.py
```

Per aggiungere un competitor: basta aggiungere `{"nome": "...", "citta": "Lido di Camaiore"}` in `competitors.json`. L'URL viene trovato automaticamente al primo run.

Per debuggare una pagina Booking: `python debug_context.py "Nome Hotel"`.

---

## ROADMAP

- [ ] Run schedulato settimanale (cron o `/schedule`)
- [ ] Notifica via email/Telegram quando i prezzi cambiano significativamente
- [ ] Supporto multi-valuta (ora fisso EUR)
