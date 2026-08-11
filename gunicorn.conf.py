# ============================================================
# Gunicorn Configuration for RegiManager
# ============================================================
# Usage: gunicorn -c gunicorn.conf.py RegiManager.wsgi:application
# ============================================================

import multiprocessing

# --- Binding ---
bind = "127.0.0.1:8000"

# --- Workers ---
# Rule of thumb: (2 × CPU cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1
# gevent keeps concurrency high under many short portal polls / any leftover wait holds.
# sync workers exhaust quickly and nginx surfaces that as 504 Gateway Time-out.
worker_class = "gevent"

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
