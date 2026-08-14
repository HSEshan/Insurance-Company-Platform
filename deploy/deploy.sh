#!/usr/bin/env bash
# Shared VPS helper: machine bootstrap + Let's Encrypt. Not Ansible.
#
# Nginx / reverse-proxy / app ports are per project — this script does not
# install an app vhost. After certs, copy that project's nginx example into
# /etc/nginx/sites-available/$APP_NAME (see deploy/nginx/ for this repo).
#
# Once per droplet:   ./deploy/deploy.sh bootstrap
# Once per project:   cp deploy/deploy.conf.example deploy/deploy.conf
#                     ./deploy/deploy.sh certs
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

SKIP_DNS=0
CONF_PATH=""

usage() {
  cat <<'EOF'
Usage: deploy/deploy.sh <command> [options]

Commands:
  bootstrap   Once per VPS: packages, Docker, UFW 22/80/443, /opt/apps
  certs       Issue Let's Encrypt certs if missing (needs DNS)
  status      Show DNS, cert paths, and the HTTP ACME stub
  help        This text

Options:
  -c FILE     Path to deploy.conf (default: deploy/deploy.conf next to this script)
  --skip-dns  Do not require DOMAINS to resolve to this VPS

Copy deploy/deploy.sh + deploy.conf.example into the next repo. Point DOMAINS
at that app's hostnames. Configure Nginx yourself for that stack's ports.

DNS at the registrar is still manual.
EOF
}

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

parse_args() {
  local args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -c)
        [[ $# -ge 2 ]] || die "-c requires a path"
        CONF_PATH=$2
        shift 2
        ;;
      --skip-dns) SKIP_DNS=1; shift ;;
      -h|--help) args+=(help); shift ;;
      *) args+=("$1"); shift ;;
    esac
  done
  COMMAND=${args[0]:-help}
}

load_conf() {
  if [[ -z "$CONF_PATH" ]]; then
    CONF_PATH="$SCRIPT_DIR/deploy.conf"
  fi
  [[ -f "$CONF_PATH" ]] || die "No $CONF_PATH — copy deploy/deploy.conf.example and edit."
  # shellcheck disable=SC1090
  source "$CONF_PATH"

  : "${APP_NAME:?APP_NAME is required in deploy.conf}"
  : "${CERTBOT_EMAIL:?CERTBOT_EMAIL is required in deploy.conf}"
  : "${DOMAINS:?DOMAINS is required in deploy.conf (space-separated hostnames)}"

  # shellcheck disable=SC2206
  DOMAIN_LIST=($DOMAINS)
  PRIMARY_DOMAIN=${DOMAIN_LIST[0]}
  SITE_NAME=${SITE_NAME:-$APP_NAME}

  if [[ "$PRIMARY_DOMAIN" == *example.com* ]] || [[ "$CERTBOT_EMAIL" == *example.com* ]]; then
    die "Edit $CONF_PATH — DOMAINS / CERTBOT_EMAIL still look like placeholders."
  fi
}

cmd_bootstrap() {
  need_cmd sudo
  log "Installing OS packages"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl git nginx certbot python3-certbot-nginx dnsutils ufw

  if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "${SUDO_USER:-$USER}"
    log "Added ${SUDO_USER:-$USER} to docker group — log out/in before Compose"
  fi

  sudo mkdir -p /opt/apps /var/www/certbot
  if [[ -n "${SUDO_USER:-}" ]]; then
    sudo chown "${SUDO_USER}:${SUDO_USER}" /opt/apps
  fi

  log "UFW: allow OpenSSH, 80, 443"
  sudo ufw allow OpenSSH
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  if ! sudo ufw status | grep -q "Status: active"; then
    sudo ufw --force enable
  fi

  sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
  sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
  sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

  log "Bootstrap done. Next: edit deploy.conf, then ./deploy/deploy.sh certs"
}

vps_ipv4() {
  curl -4 -fsS --max-time 5 https://api.ipify.org || true
}

dns_a() {
  local host=$1
  if command -v dig >/dev/null 2>&1; then
    dig +short A "$host" | grep -E '^[0-9.]+$' | head -n1
  else
    getent ahostsv4 "$host" | awk '{print $1; exit}'
  fi
}

check_dns() {
  [[ "$SKIP_DNS" -eq 1 ]] && return 0
  local ip expected host
  ip=$(vps_ipv4)
  [[ -n "$ip" ]] || die "could not detect public IPv4 (try --skip-dns)"
  for host in "${DOMAIN_LIST[@]}"; do
    expected=$(dns_a "$host")
    [[ "$expected" == "$ip" ]] || die \
      "$host resolves to '${expected:-nothing}', this VPS is $ip. Fix DNS or pass --skip-dns."
  done
  log "DNS OK (${DOMAINS} → $ip)"
}

cert_exists() {
  [[ -f "/etc/letsencrypt/live/${PRIMARY_DOMAIN}/fullchain.pem" ]]
}

site_has_tls() {
  local site="/etc/nginx/sites-available/${SITE_NAME}"
  [[ -f "$site" ]] && grep -qE 'listen[[:space:]]+443' "$site"
}

install_acme_stub() {
  local stub="/etc/nginx/sites-available/${SITE_NAME}"
  if site_has_tls; then
    log "Leaving existing TLS site $stub in place"
    return 0
  fi
  sudo tee "$stub" >/dev/null <<EOF
# HTTP ACME stub written by deploy/deploy.sh.
# Replace this file with the project's Nginx vhost after certificates exist.
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAINS};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 404;
    }
}
EOF
  sudo mkdir -p /var/www/certbot
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo ln -sfn "$stub" "/etc/nginx/sites-enabled/${SITE_NAME}"
  sudo nginx -t
  sudo systemctl reload nginx
}

cmd_certs() {
  need_cmd sudo
  need_cmd certbot
  check_dns
  if cert_exists; then
    log "Certificate already present for $PRIMARY_DOMAIN"
    log "PEM: /etc/letsencrypt/live/${PRIMARY_DOMAIN}/fullchain.pem"
    log "Configure Nginx for this project, then: sudo nginx -t && sudo systemctl reload nginx"
    return 0
  fi
  log "Issuing certificate for: ${DOMAINS}"
  install_acme_stub
  local certbot_args=(certonly --webroot -w /var/www/certbot --agree-tos
    -m "$CERTBOT_EMAIL" --non-interactive)
  local host
  for host in "${DOMAIN_LIST[@]}"; do
    certbot_args+=(-d "$host")
  done
  sudo certbot "${certbot_args[@]}"
  log "Certs: /etc/letsencrypt/live/${PRIMARY_DOMAIN}/"
  log "Next: install this project's Nginx site over /etc/nginx/sites-available/${SITE_NAME}"
}

cmd_status() {
  local host ip
  ip=$(vps_ipv4)
  printf 'VPS IPv4: %s\n' "${ip:-unknown}"
  for host in "${DOMAIN_LIST[@]}"; do
    printf 'DNS %s → %s\n' "$host" "$(dns_a "$host" || true)"
  done
  if cert_exists; then
    printf 'cert: /etc/letsencrypt/live/%s/fullchain.pem\n' "$PRIMARY_DOMAIN"
    sudo openssl x509 -in "/etc/letsencrypt/live/${PRIMARY_DOMAIN}/fullchain.pem" \
      -noout -dates -ext subjectAltName 2>/dev/null || true
  else
    printf 'cert: missing\n'
  fi
  if [[ -f "/etc/nginx/sites-available/${SITE_NAME}" ]]; then
    printf 'nginx site: /etc/nginx/sites-available/%s\n' "$SITE_NAME"
  else
    printf 'nginx site: not installed yet\n'
  fi
}

parse_args "$@"

case "$COMMAND" in
  help) usage ;;
  bootstrap) cmd_bootstrap ;;
  certs|status)
    load_conf
    "cmd_$COMMAND"
    ;;
  setup)
    die "setup was removed — run: $0 certs   then configure Nginx for this project"
    ;;
  nginx|up|seed|logs|down)
    die "$COMMAND is stack-specific. Use this project's Compose/Nginx files (see deploy/README.md)."
    ;;
  *)
    usage
    die "unknown command: $COMMAND"
    ;;
esac
