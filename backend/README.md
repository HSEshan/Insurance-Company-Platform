
## Production (VPS)

Use the **standalone** prod Compose file (do not merge with the local compose file):

```bash
cp backend/.env.production.example backend/.env.production   # edit secrets
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed
```

- App/API/MinIO bind to `127.0.0.1` only; host Nginx + TLS: [`deploy/nginx/insureco.conf.example`](./deploy/nginx/insureco.conf.example)
- Local demos still use `docker compose up` (`docker-compose.yml`)
