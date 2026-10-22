#!/bin/sh
# На VPS (Ubuntu/Debian), из папки flowers: sudo sh deploy.sh  -> https://<IP-с-дефисами>.nip.io
set -e
apt-get update -qq
apt-get install -y -qq python3 curl caddy || {
  apt-get install -y -qq debian-keyring curl gnupg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy.gpg
  echo "deb [signed-by=/usr/share/keyrings/caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" > /etc/apt/sources.list.d/caddy.list
  apt-get update -qq && apt-get install -y -qq caddy python3; }
DIR=$(cd "$(dirname "$0")" && pwd)
[ -f "$DIR/.env" ] || cp "$DIR/.env.example" "$DIR/.env"
IP=$(curl -s4 ifconfig.me); HOST="$(echo "$IP" | tr . -).nip.io"
cat > /etc/systemd/system/flowers.service <<U
[Unit]
After=network.target
[Service]
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
Environment=PORT=8080
ExecStart=/usr/bin/python3 $DIR/app.py
Restart=always
[Install]
WantedBy=multi-user.target
U
printf '%s {\n  reverse_proxy 127.0.0.1:8080\n}\n' "$HOST" > /etc/caddy/Caddyfile
systemctl daemon-reload && systemctl enable --now flowers && systemctl restart flowers caddy
echo "Готово: https://$HOST   админка: https://$HOST/admin"
