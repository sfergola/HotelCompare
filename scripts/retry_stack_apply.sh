#!/bin/bash
# Riprova l'apply dello stack Oracle Resource Manager ogni 5 minuti
# finché la VM non viene creata (out of capacity è l'errore atteso).
# Gira sul PC locale. Usa OCI CLI configurato con ~/.oci/config
#
# Uso: ./retry_stack_apply.sh

STACK_ID="ocid1.ormstack.oc1.eu-frankfurt-1.amaaaaaahbz3gsia2mkstry2a3urgc7jgxpc5n5jdbrkzt66mpoaljhvvzoq"
RETRY_INTERVAL=300   # secondi tra un tentativo e l'altro
POLL_INTERVAL=30     # secondi tra un check di stato e l'altro
POLL_MAX=9           # max poll per job (9×30s = 270s < 300s — no overlap)

OCI=$(command -v oci 2>/dev/null || echo "$HOME/.local/bin/oci")
if [ ! -x "$OCI" ]; then
    echo "Errore: OCI CLI non trovato. Installa con: pip install oci-cli"
    exit 1
fi

echo "Avvio retry loop — apply ogni 5 minuti finché la VM non viene creata."
echo "Ctrl+C per fermare."
echo ""

while true; do
    echo "[$(date '+%H:%M:%S')] Lancio apply stack..."

    JOB_ID=$("$OCI" resource-manager job create-apply-job \
        --stack-id "$STACK_ID" \
        --execution-plan-strategy AUTO_APPROVED \
        --query 'data.id' \
        --raw-output 2>/dev/null)

    if [ -z "$JOB_ID" ]; then
        echo "  → Errore nel creare il job. Riprovo tra 5 minuti."
        sleep $RETRY_INTERVAL
        continue
    fi

    echo "  → Job creato: $JOB_ID"
    echo "  → Attendo completamento..."

    for i in $(seq 1 $POLL_MAX); do
        sleep $POLL_INTERVAL
        STATUS=$("$OCI" resource-manager job get \
            --job-id "$JOB_ID" \
            --query 'data."lifecycle-state"' \
            --raw-output 2>/dev/null)
        echo "  [$(date '+%H:%M:%S')] Stato: $STATUS"

        if [ "$STATUS" = "SUCCEEDED" ]; then
            echo ""
            echo "VM creata con successo!"
            notify-send "Oracle VM" "VM hotelcompare pronta!" 2>/dev/null
            exit 0
        fi

        if [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "CANCELED" ]; then
            echo "  → Job fallito (probabilmente out of capacity). Riprovo tra 5 minuti."
            break
        fi
    done

    echo "Attendo 5 minuti..."
    sleep $RETRY_INTERVAL
done
