#!/usr/bin/env bash
#
# deploy.sh — Bootstrap the AICompanion telemetry receiver on an Ubuntu
# Amazon Lightsail instance for production.
#
# What it does:
#   1. Installs PostgreSQL, nginx, Python 3, ufw
#   2. Copies server.py + database.py into /opt/telemetry
#   3. Creates a Python venv and installs server dependencies
#   4. Creates the `telemetry` database role + database (idempotent)
#   5. Generates a strong DB password + API key if not already present
#   6. Installs the systemd service + nginx site and starts everything
#   7. Configures UFW (SSH + HTTP)
#
# Usage (run as ubuntu, sudo is used internally):
#   bash deploy/deploy.sh
#
# Re-running is safe. To change secrets, edit /etc/telemetry/env then:
#   sudo systemctl restart telemetry

set -euo pipefail

# --- Locations -------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${1:-$(dirname "$SCRIPT_DIR")}"   # repo root (parent of deploy/)
APP_DIR=/opt/telemetry
ENV_FILE=/etc/telemetry/env
SERVICE_FILE=/etc/systemd/system/telemetry.service
NGINX_SITE=/etc/nginx/sites-available/telemetry
NGINX_ENABLED=/etc/nginx/sites-enabled/telemetry
DB_NAME=telemetry
DB_USER=telemetry

echo "==> [1/8] Installing system packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv python3-pip \
    postgresql postgresql-contrib \
    nginx ufw curl >/dev/null

echo "==> [2/8] Creating app directory + service user"
sudo mkdir -p "$APP_DIR" /etc/telemetry
if ! id "telemetry" &>/dev/null; then
    sudo useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin telemetry
fi

echo "==> [3/8] Copying application files"
sudo cp "$SRC_DIR/server.py" "$SRC_DIR/database.py" "$APP_DIR/"
sudo cp "$SCRIPT_DIR/requirements-server.txt" "$APP_DIR/"

echo "==> [4/8] Creating Python venv + dependencies"
sudo -u telemetry python3 -m venv "$APP_DIR/venv"
sudo -u telemetry "$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u telemetry "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements-server.txt"

echo "==> [5/8] Writing secrets to $ENV_FILE"
sudo install -d -m 700 /etc/telemetry
if [ ! -f "$ENV_FILE" ]; then
    DB_PASS="$("$APP_DIR/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    API_KEY="$("$APP_DIR/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
    sudo bash -c "cat > $ENV_FILE" <<EOF
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME
TELEMETRY_API_KEY=$API_KEY
HOST=127.0.0.1
PORT=7999
GUNICORN_WORKERS=2
EOF
    sudo chmod 600 "$ENV_FILE"
    echo "    - Generated new secrets (see $ENV_FILE)"
else
    echo "    - $ENV_FILE already exists, keeping existing secrets"
fi
# shellcheck disable=SC1091
. "$ENV_FILE"

echo "==> [6/8] Setting up PostgreSQL role + database"
sudo -u postgres psql -v ON_ERROR_STOP=1 --quiet <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
      CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';
   END IF;
END
\$\$;
SQL
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

echo "    - Creating database schema"
cd "$APP_DIR"
sudo -u telemetry env DATABASE_URL="$DATABASE_URL" \
    "$APP_DIR/venv/bin/python" -c \
    "import asyncio; from database import init_db; asyncio.run(init_db())"

echo "==> [7/8] Installing systemd service + nginx site"
sudo cp "$SCRIPT_DIR/telemetry.service" "$SERVICE_FILE"
sudo cp "$SCRIPT_DIR/telemetry-nginx.conf" "$NGINX_SITE"
sudo ln -sf "$NGINX_SITE" "$NGINX_ENABLED"
sudo nginx -t >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now telemetry
sudo systemctl reload nginx

echo "==> [8/8] Configuring firewall (SSH + HTTP)"
sudo ufw allow OpenSSH >/dev/null
sudo ufw allow 'Nginx Full' >/dev/null
echo "y" | sudo ufw enable >/dev/null

echo
echo "===================================================================="
echo " Deployment complete."
echo "===================================================================="
PUBLIC_IP="$(curl -s -4 https://ifconfig.me || echo '?')"
echo " Health:  curl http://${PUBLIC_IP}/health"
echo " API key: $(grep TELEMETRY_API_KEY "$ENV_FILE" | cut -d= -f2)"
echo
echo " Client must send:"
echo "   POST http://${PUBLIC_IP}/api/events"
echo "   Header: X-Api-Key: <above key>"
echo
echo " Useful commands:"
echo "   sudo systemctl status telemetry          # service status"
echo "   sudo journalctl -u telemetry -f          # live logs"
echo "   sudo -u postgres psql -d $DB_NAME        # query the database"
echo
echo " For HTTPS: point a domain at ${PUBLIC_IP}, then"
echo "   sudo certbot --nginx -d telemetry.example.com"
echo "===================================================================="
