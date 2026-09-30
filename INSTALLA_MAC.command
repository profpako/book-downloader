#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
/bin/bash install_mac.sh
status=$?
if [[ $status -ne 0 && $status -ne 130 ]]; then
  echo
  read -r -p "Installazione interrotta. Premi Invio per chiudere."
fi
exit "$status"
