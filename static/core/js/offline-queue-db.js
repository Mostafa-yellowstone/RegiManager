/*
 * RegiManager offline queue storage + replay. Loaded by both the page and the service worker.
 * Changes made while offline (or while the server is down) are stored in IndexedDB and replayed
 * in order, with the same X-Idempotency-Key, once the server answers again.
 */
(function (root) {
    'use strict';

    var DB_NAME = 'regimanager-offline';
    var DB_VERSION = 1;
    var REQUESTS = 'requests';
    var META = 'meta';
    var CHANNEL = 'rm-offline-queue';
    var LOGIN_PATH = '/auth/login/';
    var MAX_BODY_BYTES = 25 * 1024 * 1024;
    var UNSAFE = { POST: 1, PUT: 1, PATCH: 1, DELETE: 1 };
    var RETRY_STATUSES = { 409: 1, 502: 1, 503: 1, 504: 1 };

    // Writes that need a live answer (searches, OCR, previews, downloads) or carry credentials are never queued.
    var SKIP_PREFIX = /^\/(auth|admin|api|sign|static|media|i18n)\//i;
    var SKIP_SEGMENT = /(^|\/)([^\/]*(ocr|search|preview|lookup|import|export|backup|restore|heartbeat|logout|login|password|esign|signature)[^\/]*|wait|pdf|print)(\/|$)|\.pdf$/i;

    var dbPromise = null;

    function openDb() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise(function (resolve, reject) {
            var request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = function () {
                var db = request.result;
                if (!db.objectStoreNames.contains(REQUESTS)) {
                    db.createObjectStore(REQUESTS, { keyPath: 'key' }).createIndex('createdAt', 'createdAt');
                }
                if (!db.objectStoreNames.contains(META)) {
                    db.createObjectStore(META, { keyPath: 'name' });
                }
            };
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { dbPromise = null; reject(request.error); };
        });
        return dbPromise;
    }

    function run(storeName, mode, work) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(storeName, mode);
                var result;
                Promise.resolve(work(tx.objectStore(storeName))).then(function (value) { result = value; });
                tx.oncomplete = function () { resolve(result); };
                tx.onerror = function () { reject(tx.error); };
                tx.onabort = function () { reject(tx.error); };
            });
        });
    }

    function requestResult(req) {
        return new Promise(function (resolve, reject) {
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function putItem(item) { return run(REQUESTS, 'readwrite', function (s) { return requestResult(s.put(item)); }); }
    function deleteItem(key) { return run(REQUESTS, 'readwrite', function (s) { return requestResult(s.delete(key)); }); }
    function getItem(key) { return run(REQUESTS, 'readonly', function (s) { return requestResult(s.get(key)); }); }

    function listItems(userId) {
        return run(REQUESTS, 'readonly', function (s) { return requestResult(s.index('createdAt').getAll()); })
            .then(function (items) {
                items = items || [];
                if (userId === undefined) return items;
                return items.filter(function (item) { return (item.userId || '') === (userId || ''); });
            });
    }

    function getMeta(name) {
        return run(META, 'readonly', function (s) { return requestResult(s.get(name)); })
            .then(function (row) { return row ? row.value : null; });
    }

    function setMeta(name, value) {
        return run(META, 'readwrite', function (s) { return requestResult(s.put({ name: name, value: value })); });
    }

    function broadcast(message) {
        try {
            var channel = new BroadcastChannel(CHANNEL);
            channel.postMessage(message);
            channel.close();
        } catch (e) { /* BroadcastChannel unsupported */ }
    }

    function isQueueable(method, url) {
        if (!UNSAFE[String(method || '').toUpperCase()]) return false;
        var parsed = new URL(url, root.location.href);
        if (parsed.origin !== root.location.origin) return false;
        return !SKIP_PREFIX.test(parsed.pathname) && !SKIP_SEGMENT.test(parsed.pathname);
    }

    function newKey() {
        if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
        var bytes = new Uint8Array(16);
        root.crypto.getRandomValues(bytes);
        return Array.prototype.map.call(bytes, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
    }

    function retryAfterMs(response, fallback) {
        var seconds = parseInt(response.headers.get('Retry-After') || '', 10);
        return (isFinite(seconds) && seconds > 0 ? seconds : fallback) * 1000;
    }

    function buildBody(item, csrfToken) {
        var contentType = item.headers['content-type'] || '';
        var lower = contentType.toLowerCase();
        var isUrlEncoded = lower.indexOf('application/x-www-form-urlencoded') === 0;
        var isMultipart = lower.indexOf('multipart/form-data') === 0;
        if (!item.body || !(isUrlEncoded || isMultipart)) {
            return Promise.resolve({ body: item.body || null, contentType: contentType || null });
        }
        // Re-encode form bodies so the CSRF field matches the current session (it rotates on sign-in).
        return new Response(item.body, { headers: { 'Content-Type': contentType } }).formData().then(function (form) {
            if (csrfToken && form.has('csrfmiddlewaretoken')) form.set('csrfmiddlewaretoken', csrfToken);
            if (isUrlEncoded) {
                return { body: new URLSearchParams(form).toString(), contentType: 'application/x-www-form-urlencoded;charset=UTF-8' };
            }
            return { body: form, contentType: null };
        });
    }

    function replayOne(item, ctx) {
        return buildBody(item, ctx.csrfToken).then(function (built) {
            var headers = new Headers();
            ['accept', 'x-requested-with'].forEach(function (name) {
                if (item.headers[name]) headers.set(name, item.headers[name]);
            });
            if (built.contentType) headers.set('Content-Type', built.contentType);
            headers.set('X-Idempotency-Key', item.key);
            headers.set('X-Offline-Replay', '1');
            if (ctx.csrfToken) headers.set('X-CSRFToken', ctx.csrfToken);
            return fetch(item.url, {
                method: item.method,
                headers: headers,
                body: built.body,
                credentials: 'same-origin',
                redirect: 'follow',
                cache: 'no-store',
            });
        }).then(function (response) {
            if (response.status === 429) return { outcome: 'wait', delay: retryAfterMs(response, 60) };
            if (RETRY_STATUSES[response.status] || response.headers.get('X-Regi-Retryable')) {
                return { outcome: 'wait', delay: retryAfterMs(response, 30) };
            }
            var finalPath = '';
            try { finalPath = new URL(response.url).pathname; } catch (e) { /* opaque */ }
            if (response.status === 401 || (response.redirected && finalPath.indexOf(LOGIN_PATH) === 0)) {
                return { outcome: 'auth' };
            }
            if (response.headers.get('X-Idempotent-Replay')) return { outcome: 'done' };
            if (response.status >= 400) return { outcome: 'failed', status: response.status };
            var isHtml = (response.headers.get('Content-Type') || '').indexOf('text/html') !== -1;
            // A form that re-renders (no redirect) usually means validation errors the user should look at.
            if (item.kind === 'form' && !response.redirected && isHtml) return { outcome: 'review', status: response.status };
            return { outcome: 'done' };
        }, function () {
            return { outcome: 'wait', delay: 15000, offline: true };
        });
    }

    function withLock(work) {
        if (root.navigator && root.navigator.locks && root.navigator.locks.request) {
            return root.navigator.locks.request('rm-offline-replay', { ifAvailable: true }, function (lock) {
                return lock ? work() : null;
            });
        }
        return work();
    }

    /** Replay this user's queue in order. ctx = { userId, csrfToken }. */
    function replayAll(ctx) {
        return withLock(function () {
            var summary = { synced: 0, review: 0, failed: 0, auth: false, waitMs: 0, remaining: 0, source: ctx.source || 'worker' };
            return listItems(ctx.userId).then(function (items) {
                var queue = items.filter(function (item) { return item.status !== 'failed' && item.status !== 'review'; });
                function next(index) {
                    if (index >= queue.length) return summary;
                    var item = queue[index];
                    return replayOne(item, ctx).then(function (result) {
                        item.attempts = (item.attempts || 0) + 1;
                        item.lastTriedAt = Date.now();
                        if (result.outcome === 'done') {
                            summary.synced += 1;
                            return deleteItem(item.key).then(function () { return next(index + 1); });
                        }
                        if (result.outcome === 'wait') {
                            summary.waitMs = result.delay;
                            item.status = 'pending';
                            return putItem(item).then(function () { return summary; });
                        }
                        if (result.outcome === 'auth') {
                            summary.auth = true;
                            item.status = 'auth';
                            return putItem(item).then(function () { return summary; });
                        }
                        item.status = result.outcome;
                        item.httpStatus = result.status || 0;
                        summary[result.outcome] += 1;
                        return putItem(item).then(function () { return next(index + 1); });
                    });
                }
                return next(0);
            }).then(function (result) {
                return listItems(ctx.userId).then(function (left) {
                    result.remaining = left.length;
                    broadcast({ type: 'changed', summary: result });
                    return result;
                });
            });
        });
    }

    root.RMOfflineDB = {
        MAX_BODY_BYTES: MAX_BODY_BYTES,
        putItem: putItem,
        getItem: getItem,
        deleteItem: deleteItem,
        listItems: listItems,
        getMeta: getMeta,
        setMeta: setMeta,
        broadcast: broadcast,
        isQueueable: isQueueable,
        newKey: newKey,
        replayAll: replayAll,
        CHANNEL: CHANNEL,
    };
})(self);
