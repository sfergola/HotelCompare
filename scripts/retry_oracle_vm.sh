#!/bin/bash
# Riprova la creazione VM Oracle ogni 5 minuti finché non riesce.
# Richiede OCI CLI configurato: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm
#
# Uso: ./retry_oracle_vm.sh

COMPARTMENT_ID="ocid1.tenancy.oc1..<il-tuo-tenancy-ocid>"
SUBNET_ID="ocid1.subnet.oc1.eu-frankfurt-1..<il-tuo-subnet-ocid>"
SSH_KEY_FILE="$HOME/.ssh/id_hotelcompare.pub"
AVAILABILITY_DOMAINS=("EU-FRANKFURT-1-AD-1" "EU-FRANKFURT-1-AD-2" "EU-FRANKFURT-1-AD-3")

echo "Avvio retry loop — proverò ogni 5 minuti su tutti e 3 gli AD."
echo "Ctrl+C per fermare."

while true; do
    for AD in "${AVAILABILITY_DOMAINS[@]}"; do
        echo "[$(date '+%H:%M:%S')] Provo AD: $AD ..."
        RESULT=$(oci compute instance launch \
            --compartment-id "$COMPARTMENT_ID" \
            --availability-domain "$AD" \
            --shape "VM.Standard.A1.Flex" \
            --shape-config '{"ocpus": 2, "memoryInGBs": 12}' \
            --image-id "$(oci compute image list --compartment-id "$COMPARTMENT_ID" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape "VM.Standard.A1.Flex" --query 'data[0].id' --raw-output 2>/dev/null)" \
            --subnet-id "$SUBNET_ID" \
            --display-name "hotelcompare" \
            --ssh-authorized-keys-file "$SSH_KEY_FILE" \
            --assign-public-ip true \
            2>&1)

        if echo "$RESULT" | grep -q '"lifecycle-state": "PROVISIONING"'; then
            echo "VM creata! Controlla la console Oracle."
            notify-send "Oracle VM" "VM hotelcompare in provisioning!" 2>/dev/null
            exit 0
        else
            echo "  → Out of capacity o errore. Riprovo tra poco."
        fi
    done
    echo "Attendo 5 minuti..."
    sleep 300
done
