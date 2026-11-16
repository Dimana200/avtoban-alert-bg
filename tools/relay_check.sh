#!/bin/bash
# Avtoban Alert BG - check from the server in Sofia: can it reach the National Access Point, and what does robots.txt allow?
# Reads only: robots.txt and the start pages. Downloads nothing else.
UA="AvtobanAlertBG/1.0 (road safety app; https://dimana200.github.io/avtoban-alert-bg/)"
for h in datasheet.api.bg traffic.api.bg; do
  echo "===== $h"
  code=$(curl -s -m 20 -A "$UA" -o /tmp/r.txt -w "%{http_code}" "https://$h/robots.txt")
  echo "robots.txt: HTTP $code"
  [ "$code" = 200 ] && grep -iE "user-agent|disallow|allow|crawl" /tmp/r.txt | head -12
  code=$(curl -sL -m 20 -A "$UA" -o /tmp/h.html -w "%{http_code} %{size_download}" "https://$h/")
  echo "start page: HTTP $code bytes"
done
echo "===== links to datasets on datasheet.api.bg"
grep -oE 'href="[^"#]+"' /tmp/h.html >/dev/null 2>&1
curl -sL -m 20 -A "$UA" https://datasheet.api.bg/ | grep -oE 'href="[^"#]+"' | cut -d'"' -f2 | grep -viE '\.(css|js|png|ico|svg)$' | sort -u | head -25
echo "===== done"
