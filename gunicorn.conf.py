# ============================================================
# Gunicorn Configuration for RegiManager
# ============================================================
# Usage: gunicorn -c gunicorn.conf.py RegiManager.wsgi:application
# ============================================================

import multiprocessing

# --- Binding ---
bind = "127.0.0.1:8000"

# --- Workers ---
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"

# --- Timeout ---
timeout = 120
graceful_timeout = 30
keepalive = 5

# --- Logging ---
accesslog = "-"
errorlog = "-"
loglevel = "info"

proc_name = "regimanager"

limit_request_line = 8190
limit_request_fields = 200
