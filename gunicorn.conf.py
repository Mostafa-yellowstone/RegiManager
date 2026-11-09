# ============================================================
# Gunicorn Configuration for RegiManager
# ============================================================
# Usage: gunicorn -c gunicorn.conf.py RegiManager.wsgi:application
# ============================================================

import multiprocessing
import os

# --- Binding ---
bind = "127.0.0.1:8000"

# --- Workers ---
# Rule of thumb: (2 × CPU cores) + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
# gevent keeps concurrency high under many short portal polls / any leftover wait holds.
# sync workers exhaust quickly and nginx surfaces that as 504 Gateway Time-out.
worker_class = "gevent"
# Each open request can hold its own Postgres connection, so this caps connections per worker.
# workers × worker_connections must stay below Postgres max_connections.
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "100"))

# Recycle workers periodically so slow memory growth (PDF/image work) can't build up into OOM kills (502s).
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "200"))

# Under gevent every request runs in its own greenlet with its own DB connection; a persistent
# connection is never reused by a later request and only piles up idle Postgres connections.
raw_env = [f"DB_CONN_MAX_AGE={os.getenv('DB_CONN_MAX_AGE', '0')}"]

# --- Timeout ---
# CRITICAL: Must be long enough for:
#   - Large file uploads (up to 50MB)
#   - PDF generation (can take 5-10s for complex forms)
#   - Long database queries
timeout = 120  # 2 minutes

# Graceful timeout for worker restart
graceful_timeout = 30

# --- Keep-alive ---
keepalive = 5  # seconds to wait for next request on a keep-alive connection

# --- Logging ---
accesslog = "-"       # stdout
errorlog  = "-"       # stdout
loglevel  = "info"

# --- Process Naming ---
proc_name = "regimanager"

# --- Security ---
limit_request_line   = 8190
limit_request_fields = 200


def post_fork(server, worker):
    # psycopg2 is a C driver: without this, every query blocks the whole gevent worker,
    # so one slow query (or a long-poll loop) stalls all requests on it and nginx returns 502/504.
    try:
        from psycogreen.gevent import patch_psycopg
    except ImportError:
        server.log.warning("psycogreen is not installed; Postgres queries will block gevent workers.")
        return
    patch_psycopg()
