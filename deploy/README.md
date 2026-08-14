# Deploy helpers (committed)

| Path | Purpose |
|---|---|
| `deploy.sh` | **Shared:** VPS bootstrap + Let's Encrypt. No app proxy. |
| `deploy.conf.example` | Copy to `deploy.conf` on the server (gitignored) — app name, domains, email |
| `nginx/insureco.conf.example` | **This app only:** SPA `:8080` + API `:8000` + MinIO `:9000` |
| `nginx/reverse-proxy.conf.example` | Older single-host sketch (superseded) |
| `../docker-compose.prod.yml` | This app's production Compose (localhost binds) |
| `../backend/.env.production.example` | This app's env template |

Personal narrative lives in `DEPLOY.md` at the repo root (gitignored).

## What the script owns vs what you own

| Script (`deploy.sh`) | Per project |
|---|---|
| Docker, Nginx package, Certbot, UFW 22/80/443 | Compose / runtime |
| One cert covering `DOMAINS` | Host ports (`127.0.0.1:…`) |
| HTTP ACME stub until you replace it | `/etc/nginx/sites-available/<app>` proxy vhost |

Copy `deploy.sh` + `deploy.conf.example` into the next repo. Write a new Nginx
site for that stack. Do not reuse `insureco.conf.example` unless the ports match.

## Once per droplet

```bash
cd /opt/apps/insurance-platform
chmod +x deploy/deploy.sh
./deploy/deploy.sh bootstrap
# log out/in if Docker was just installed (docker group)
```

## Once per project (TLS)

DNS A records for every name in `DOMAINS` must already point at the VPS.

```bash
cp deploy/deploy.conf.example deploy/deploy.conf
nano deploy/deploy.conf
./deploy/deploy.sh certs
```

Then install **this** app's vhost (replace `YOURDOMAIN`):

```bash
sudo cp deploy/nginx/insureco.conf.example /etc/nginx/sites-available/insureco
sudo nano /etc/nginx/sites-available/insureco
sudo ln -sfn /etc/nginx/sites-available/insureco /etc/nginx/sites-enabled/insureco
sudo nginx -t && sudo systemctl reload nginx
```

Bring the stack up separately:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

## Later updates

```bash
git pull
docker compose -f docker-compose.prod.yml up --build -d
# only reload Nginx if you changed the vhost file
```

## Commands

```
./deploy/deploy.sh bootstrap
./deploy/deploy.sh certs
./deploy/deploy.sh status
```
