#!/usr/bin/env bash
# One-command deploy on a fresh Linux VPS (Ubuntu/Debian):  ./deploy.sh
# Serves the panel and webhooks at https://<your-ip>.nip.io with a Let's Encrypt certificate.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

IP="${PUBLIC_IP:-$(curl -fsS https://api.ipify.org)}"
SUFFIX="${DOMAIN_SUFFIX:-nip.io}"  # sslip.io works the same way if nip.io hits a certificate rate limit
DOMAIN="${IP//./-}.${SUFFIX}"

[ -f .env ] || cp .env.example .env
set_env() {
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
set_env DOMAIN "$DOMAIN"
set_env PUBLIC_URL "https://$DOMAIN"
if ! grep -Eq '^PANEL_PASSWORD=.{10,}' .env; then
  set_env PANEL_PASSWORD "$(openssl rand -base64 18 | tr -d '/+=')"
fi

if command -v ufw >/dev/null && ufw status | grep -q active; then
  ufw allow 80/tcp && ufw allow 443/tcp
fi

docker compose up -d --build

echo
echo "Panel:    https://$DOMAIN"
echo "Password: $(grep '^PANEL_PASSWORD=' .env | cut -d= -f2-)"
echo "The first HTTPS request can take ~30 s while the certificate is issued."
