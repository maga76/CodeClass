#!/usr/bin/env bash
# Запуск команд Django на сервере с нужными настройками:
#   sudo bash /srv/codeclass/deploy/manage.sh createsuperuser
set -euo pipefail
exec runuser -u codeclass -- env $(grep -v '^#' /etc/codeclass.env | xargs) \
    /srv/codeclass/.venv/bin/python /srv/codeclass/manage.py "$@"
