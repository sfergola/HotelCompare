#!/bin/bash
# Keepalive per evitare che Oracle recami la VM Always Free per inattività.
# Va messo nel crontab della VM Oracle stessa, non del PC locale.
#
# Setup sulla VM (una tantum):
#   (crontab -l 2>/dev/null; cat /home/ubuntu/HotelCompare/scripts/oracle_keepalive.sh | grep "^# CRON:" | sed 's/# CRON: //') | crontab -
#
# CRON: 0 12 * * * echo "keepalive $(date)" >> /tmp/keepalive.log && curl -s https://www.google.com > /dev/null

echo "keepalive $(date)" >> /tmp/keepalive.log
curl -s --max-time 10 https://www.google.com > /dev/null
