#!/bin/bash
# Avtoban Alert BG relay (runs every 5 min on the server in Sofia).
# 1. updates itself from GitHub; 2. reads robots.txt of the National Access Point and publishes it;
# 3. only if config allows it AND robots.txt does not forbid it: downloads the open datasets.
# Everything it fetches is put in /var/www/relay, served on port 80 for the Avtoban Alert BG server.
OUT=/var/www/relay
UA="AvtobanAlertBG/1.0 (road safety app; https://dimana200.github.io/avtoban-alert-bg/)"
RAW=https://raw.githubusercontent.com/Dimana200/avtoban-alert-bg/main/tools/relay
date -u +%FT%TZ > $OUT/updated.txt

# self-update (only if the new script downloads completely and is a bash script)
if curl -fsSL "$RAW/run.sh" -o /opt/relay/run.new && head -1 /opt/relay/run.new | grep -q bash; then
  cmp -s /opt/relay/run.new /opt/relay/run.sh || { mv /opt/relay/run.new /opt/relay/run.sh; chmod +x /opt/relay/run.sh; }
fi
ENABLED=$(curl -fsSL "$RAW/enabled" 2>/dev/null | head -c 1)

# robots.txt and reachability of the National Access Point (read-only)
: > $OUT/status.txt
for h in datasheet.api.bg traffic.api.bg; do
  code=$(curl -s -m 20 -A "$UA" -o $OUT/robots_$h.txt -w "%{http_code}" "https://$h/robots.txt")
  home=$(curl -sL -m 20 -A "$UA" -o /dev/null -w "%{http_code}" "https://$h/")
  echo "$h robots=$code home=$home" >> $OUT/status.txt
done
echo "enabled=$ENABLED" >> $OUT/status.txt

# stop here unless switched on, and never against robots.txt
[ "$ENABLED" = "1" ] || exit 0
if grep -iqE '^[[:space:]]*disallow:[[:space:]]*/[[:space:]]*$' $OUT/robots_datasheet.api.bg.txt 2>/dev/null; then
  echo "robots.txt disallows - not downloading" >> $OUT/status.txt; exit 0
fi
mkdir -p $OUT/pages
curl -sL -m 30 -A "$UA" https://datasheet.api.bg/ -o $OUT/pages/home.html
echo "fetched start page" >> $OUT/status.txt
