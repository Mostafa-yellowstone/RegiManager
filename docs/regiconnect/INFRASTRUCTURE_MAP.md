# Infrastructure map

## Runtime

- Python 3.12 (CI). Django 6.0.x. Gunicorn gevent bind `127.0.0.1:8000` (`gunicorn.conf.py`).
- `docker-compose.yml`: Postgres 16 + Redis 7 only. **No app Dockerfile.**
- Files: local `MEDIA_ROOT`. No django-storages / S3.
- Cache: Redis when `USE_REDIS_CACHE`; else local-memory.
- Email: Django SMTP (`EMAIL_HOST*` in `.env`).

## Data stores

- Production: Postgres when `DB_NAME` is set (`psycopg2`).
- Local/tests: SQLite unless env points at Postgres.
- Redis: Celery broker/results; portal realtime pub/sub (`core/realtime.py`).

## Jobs

`RegiManager/celery.py` autodiscovers tasks. `CELERY_TASK_ALWAYS_EAGER` defaults True when `DEBUG`. Beat schedule in settings (not DatabaseScheduler):

- Daily registration reminders
- Daily insurance company license alerts
- Daily PSB license alerts
- Hourly TLC installment reminders

Email marketing batches: Celery if workers exist, else sync.

## Deploy

`.github/workflows/autodeploy.yml`:

1. `python manage.py test core` (eager Celery).
2. SSH to VPS, run `/home/Projects/sc.sh` (script **not** in repo).

Secrets: GitHub `VPS_SSH_KEY` / `VPS_USER`; app secrets live on the VPS `.env`. **No AWS Secrets Manager / Azure Key Vault / GCP SM today.**

## Observability

Python logging in settings. No OpenTelemetry in-repo. Portal uses Redis wait endpoints rather than SSE-from-Celery.

## Implications for RegiConnect

- Reuse Celery + Redis; do not add Kafka.
- Keep sync/eager fallback so CI and VPS without workers still run mock jobs.
- Store connector files on `FileField` until object storage is justified.
- Secret manager is an **adapter**: encrypted-at-rest DB blob for development; cloud SM later. Database stores `credential_reference` only.
- CI must gain `regiconnect` tests (`manage.py test core regiconnect` or include the app in the existing job).
