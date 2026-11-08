#!/usr/bin/env bash
# Установка и обновление CodeClass на сервере Ubuntu 22.04 / 24.04.
#
#   sudo bash deploy/setup.sh codeclass.example.com
#
# Запускать из папки проекта. Повторный запуск обновляет сайт до текущей версии кода.
# Домен должен уже указывать на IP сервера (A-запись), иначе Caddy не получит HTTPS-сертификат.
set -euo pipefail

DOMAIN="${1:?Укажите домен: sudo bash deploy/setup.sh codeclass.example.com}"
APP_DIR=/srv/codeclass
DATA_DIR=/var/lib/codeclass
ENV_FILE=/etc/codeclass.env
APP_USER=codeclass
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Запустите через sudo" >&2
    exit 1
fi

echo "==> Системные пакеты"
apt-get update -q
apt-get install -y -q python3 python3-venv g++ bubblewrap caddy rsync

echo "==> Пользователь и папки"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR"

echo "==> Код"
rsync -a --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude 'db.sqlite3' --exclude 'staticfiles' \
    --exclude 'desktop/build' --exclude 'desktop/dist' --exclude '.git' \
    "$SRC_DIR"/ "$APP_DIR"/
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Проверка изоляции (bubblewrap)"
bwrap_works() {
    runuser -u "$APP_USER" -- bwrap --unshare-all --die-with-parent --ro-bind /usr /usr \
        --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin \
        --proc /proc --dev /dev /usr/bin/true 2>/dev/null
}
SANDBOX=bwrap
if ! bwrap_works && [[ -d /etc/apparmor.d ]]; then
    # Ubuntu 24.04 запрещает user namespaces по умолчанию — разрешаем их только для bwrap
    cat > /etc/apparmor.d/bwrap-codeclass <<'PROFILE'
abi <abi/4.0>,
include <tunables/global>

profile bwrap-codeclass /usr/bin/bwrap flags=(unconfined) {
  userns,
}
PROFILE
    apparmor_parser -r /etc/apparmor.d/bwrap-codeclass || true
fi
if ! bwrap_works; then
    SANDBOX=none
    echo "!!! bubblewrap не работает на этом сервере — решения будут запускаться без изоляции" >&2
fi

echo "==> Настройки ($ENV_FILE)"
if [[ ! -f "$ENV_FILE" ]]; then
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
    cat > "$ENV_FILE" <<ENV
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN
DJANGO_DB_PATH=$DATA_DIR/db.sqlite3
DJANGO_TIME_ZONE=UTC
JUDGE_SANDBOX=$SANDBOX
ENV
fi
sed -i "s/^JUDGE_SANDBOX=.*/JUDGE_SANDBOX=$SANDBOX/" "$ENV_FILE"
chmod 600 "$ENV_FILE"

chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$DATA_DIR"
chmod 700 "$DATA_DIR"

manage() {
    runuser -u "$APP_USER" -- env $(grep -v '^#' "$ENV_FILE" | xargs) "$APP_DIR/.venv/bin/python" "$APP_DIR/manage.py" "$@"
}

echo "==> База данных и статика"
manage migrate --noinput
manage collectstatic --noinput -v 0

echo "==> Автозапуск (systemd)"
cp "$APP_DIR/deploy/codeclass.service" /etc/systemd/system/codeclass.service
systemctl daemon-reload
systemctl enable --now codeclass
systemctl restart codeclass

echo "==> HTTPS (Caddy)"
sed "s/{DOMAIN}/$DOMAIN/" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy || systemctl restart caddy

echo "==> Проверка запуска решений"
manage check_judge || true

cat <<DONE

Готово: https://$DOMAIN
Создать администратора:  sudo bash $APP_DIR/deploy/manage.sh createsuperuser
Логи сайта:              sudo journalctl -u codeclass -f
Настройки:               $ENV_FILE (после изменения: sudo systemctl restart codeclass)
DONE
