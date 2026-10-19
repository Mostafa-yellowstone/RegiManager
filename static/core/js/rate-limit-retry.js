/*
 * RegiManager: quietly ride out "busy" (HTTP 429) answers instead of showing an error.
 * The server turns a request away before running it, so sending it again later is always safe.
 * After a 429 every same-origin request waits out Retry-After, so a burst can't keep the limit hit.
 */
(function () {
    'use strict';

    if (!window.fetch || window.__rmBusyRetry) return;
    window.__rmBusyRetry = true;

    var nativeFetch = window.fetch.bind(window);
    var MAX_RETRIES = 2;
    var MAX_WAIT_MS = 90000;
    // Background polls already pause themselves on 429; holding them here would only delay that.
    var POLL = /\/(notifications(\/wait)?|events|quote-distribution|session-heartbeat|chat\/wait)\/?$/;
    var pausedUntil = 0;
    var notice = null;
    var noticeTimer = null;

    function retryAfterMs(response) {
        var seconds = parseInt(response.headers.get('Retry-After') || '', 10);
        return (isFinite(seconds) && seconds > 0 ? seconds : 5) * 1000;
    }

    function sleep(ms, signal) {
        return new Promise(function (resolve, reject) {
            if (signal && signal.aborted) return reject(new DOMException('Aborted', 'AbortError'));
            var timer = setTimeout(resolve, ms);
            if (signal) {
                signal.addEventListener('abort', function () {
                    clearTimeout(timer);
                    reject(new DOMException('Aborted', 'AbortError'));
                }, { once: true });
            }
        });
    }

    function showNotice() {
        if (!document.body) return;
        if (!notice) {
            notice = document.createElement('div');
            notice.setAttribute('role', 'status');
            notice.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:100001;'
                + 'background:#0f172a;color:#e2e8f0;border:1px solid rgba(148,163,184,.3);border-radius:999px;'
                + 'padding:.5rem 1rem;font:500 13px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;'
                + 'box-shadow:0 10px 30px rgba(0,0,0,.25);pointer-events:none';
            notice.textContent = 'One moment… finishing your request.';
            document.body.appendChild(notice);
        }
        notice.hidden = false;
        clearTimeout(noticeTimer);
        noticeTimer = setTimeout(hideNotice, Math.max(1500, pausedUntil - Date.now() + 1500));
    }

    function hideNotice() {
        if (notice) notice.hidden = true;
    }

    function sameOriginPath(input) {
        try {
            var url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
            return url.origin === location.origin ? url.pathname : null;
        } catch (e) {
            return null;
        }
    }

    function canResend(input, init) {
        if (typeof Request !== 'undefined' && input instanceof Request && input.bodyUsed) return false;
        var body = init && init.body;
        return !(body && typeof ReadableStream !== 'undefined' && body instanceof ReadableStream);
    }

    window.fetch = function (input, init) {
        var path = sameOriginPath(input);
        if (path === null || POLL.test(path)) return nativeFetch(input, init);

        var signal = (init && init.signal) || (input && input.signal) || null;
        var original = typeof Request !== 'undefined' && input instanceof Request ? input.clone() : input;
        var attempt = 0;

        function send() {
            var wait = pausedUntil - Date.now();
            var ready = wait > 0 ? sleep(wait, signal) : Promise.resolve();
            return ready.then(function () {
                var request = attempt === 0 ? input : (original instanceof Request ? original.clone() : original);
                return nativeFetch(request, init);
            }).then(function (response) {
                if (response.status !== 429 || attempt >= MAX_RETRIES || !canResend(original, init)) return response;
                var delay = retryAfterMs(response);
                if (delay > MAX_WAIT_MS) return response;
                attempt += 1;
                pausedUntil = Math.max(pausedUntil, Date.now() + delay);
                showNotice();
                return send();
            });
        }

        return send();
    };
})();
