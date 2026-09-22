#!/usr/bin/env bash
# Runs ON the server. Installs Docker (if missing), unpacks the project into ~/resume-builder,
# keeps an existing .env, builds and starts the stack.
#   usage: bash server-setup.sh /path/to/resume-builder.tgz|.zip [frontend_port]
set -euo pipefail

ZIP="${1:-$HOME/resume-builder.tgz}"
PORT="${2:-80}"
APP_DIR="$HOME/resume-builder"

echo "==> Checking Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "    Installing Docker Engine + Compose plugin (needs sudo)"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "    Docker installed. (Group change applies to new logins; using sudo for this run.)"
fi
DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo docker"
$DOCKER compose version >/dev/null 2>&1 || { echo "docker compose plugin missing"; exit 1; }


echo "==> Unpacking $ZIP -> $APP_DIR"
mkdir -p "$APP_DIR"
[ -f "$APP_DIR/.env" ] && cp "$APP_DIR/.env" /tmp/resume-builder.env.bak
TMP=$(mktemp -d)
case "$ZIP" in
  *.tgz|*.tar.gz) tar -xzf "$ZIP" -C "$TMP" ;;
  *.zip)
    # zips made by PowerShell's Compress-Archive use backslashes; normalise while extracting
    python3 - "$ZIP" "$TMP" <<'PY'
import sys, os, zipfile
zp, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zp) as z:
    for info in z.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("/"):
            continue
        dest = os.path.join(out, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with z.open(info) as src, open(dest, "wb") as dst:
            dst.write(src.read())
PY
    ;;
  *) echo "unknown archive type: $ZIP"; exit 1 ;;
esac
# the archive contains a top-level "resume-builder/" folder
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude data --exclude .env --exclude docker-compose.override.yml "$TMP/resume-builder/" "$APP_DIR/"
else
  cp -r "$TMP/resume-builder/." "$APP_DIR/"
fi
chmod +x "$APP_DIR"/deploy/*.sh 2>/dev/null || true
rm -rf "$TMP"
[ -f /tmp/resume-builder.env.bak ] && cp /tmp/resume-builder.env.bak "$APP_DIR/.env"

cd "$APP_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "!!  .env created from .env.example - it still has placeholder keys."
  echo "    Edit it now:   nano $APP_DIR/.env    then re-run this script (or: docker compose up -d --build)."
fi

# expose the frontend on the requested port (default 80)
cat > docker-compose.override.yml <<EOF
services:
  frontend:
    ports:
      - "${PORT}:80"
  backend:
    ports: !override []   # backend only reachable through the frontend proxy
EOF

echo "==> Building and starting (first build takes a few minutes: LibreOffice + fonts)"
$DOCKER compose up -d --build

echo
echo "==> Status"
$DOCKER compose ps
IP=$(curl -s --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 || hostname -I | awk '{print $1}')
echo
echo "Open:  http://${IP}:${PORT}   (make sure the AWS security group allows inbound TCP ${PORT})"
echo "Logs:  cd $APP_DIR && $DOCKER compose logs -f"
