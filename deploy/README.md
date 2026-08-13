# Deploy helpers (committed)

| Path | Purpose |
|---|---|
| `../docker-compose.prod.yml` | **Standalone** production Compose (localhost binds only; no merge with dev compose) |
| `nginx/insureco.conf.example` | Host Nginx: HTTPS, SPA routes, `/api` → FastAPI, `files.*` → MinIO |
| `nginx/reverse-proxy.conf.example` | Older single-host sketch (superseded by `insureco.conf.example`) |
| `../backend/.env.production.example` | Env template for the VPS |

```bash
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed
```

Personal step-by-step notes live in `DEPLOY.md` at the repo root (gitignored).
