# Scraping parallelo per-hotel con ProcessPoolExecutor

Run sequenziale richiedeva 5+ ore per ~15 hotel, surriscaldando il PC. Abbiamo scelto di lanciare ogni hotel in un processo separato (ProcessPoolExecutor, default max_workers=3), ognuno con il proprio browser Playwright.

## Considered Options

**Asyncio + async Playwright**: più veloce in teoria (I/O concorrente), ma Playwright async è più complesso e il delay intenzionale di 4-8s per query rende il vantaggio marginale rispetto al multiprocessing.

**Threading**: Playwright non è thread-safe.

**Multiprocessing scelto**: isolamento completo per processo, crash di un hotel non blocca gli altri, checkpoint per-hotel separati. Con 3 worker: ~2h invece di ~5h.

## Consequences

- RAM: ~200-400MB per browser × 3 worker = 600MB-1.2GB aggiuntivi. Configurare `max_workers=1` su PC con poca RAM.
- Checkpoint per-hotel (`partial_<hotel>_from..._to..._inprogress.json`): legato alle date esatte del run. Per riprendere un run interrotto, non cambiare le date nel config.
- `data_fine` vs `stagione_fine`: lo scheduler usa `stagione_fine` (fisso), l'utente controlla `data_fine` per run parziali manuali.
