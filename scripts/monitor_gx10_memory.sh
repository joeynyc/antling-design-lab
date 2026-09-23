#!/usr/bin/env bash
set -euo pipefail

samples="${1:-600}"
interval="${2:-2}"
printf 'timestamp_utc,mem_available_kib\n'
for ((index = 0; index < samples; index++)); do
  available="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  printf '%s,%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$available"
  sleep "$interval"
done
