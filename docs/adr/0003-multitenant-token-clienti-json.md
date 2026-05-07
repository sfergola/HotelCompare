# Architettura multi-tenant: token URL + clienti.json

Ogni cliente (hotel pagante) riceve un URL unico con token (`app.py?token=abc123`). La web app filtra automaticamente i competitor in base al token, leggendo `clienti.json` (struttura: `{ "token": { "nome": "...", "competitor": [...] } }`). `competitors.json` resta invariato: contiene il pool globale di hotel scrapati. Lo scraper non cambia. Vedere `CONTEXT.md` → `Token` e `clienti.json` per le definizioni.

## Considered Options

**Password per hotel**: richiede login, stato sessione, più complesso da implementare e da usare.

**Deploy Streamlit separato per hotel**: non scalabile, un deploy per cliente.

**Token URL scelto**: zero infrastruttura aggiuntiva, link condivisibile, nessun login. Il rischio (chiunque con il link vede i dati) è accettabile — i dati sono prezzi pubblici di Booking.com.

## Come si aggiunge un cliente

1. Ricerca manuale su Booking: stessa città, stelle simili, fascia prezzo simile.
2. Proposta lista competitor al cliente → conferma.
3. Generare token: `python -c "import secrets; print(secrets.token_urlsafe(16))"`.
4. Aggiunta voce in `clienti.json` sulla VM Oracle Cloud (vedi ADR-0002).
5. Invio link al cliente: `https://<app-url>?token=<token>`.

## Consequences

- `clienti.json` è gitignored — va ricreato manualmente sulla VM Oracle Cloud (vedi ADR-0002) dopo il provisioning. Tenere una copia di backup locale fuori dalla VM: se la VM viene persa, tutti i token clienti vanno rigenerati e i link cambiano.
- Revocare l'accesso a un cliente significa rimuovere il suo token da `clienti.json` sulla VM — non è un `git pull`, è una modifica diretta al file sulla VM.
- Il pool globale in `competitors.json` cresce man mano che si aggiungono clienti. Con molti hotel il tempo di scraping aumenta proporzionalmente.
