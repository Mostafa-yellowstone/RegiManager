{% load static %}/* RegiManager service worker: offline-queue-v2 */
{% if offline_queue_enabled %}
importScripts('{% static "core/js/offline-queue-db.js" %}?v=oq-2');

var DB = self.RMOfflineDB;
var SERVER_DOWN = { 502: 1, 503: 1, 504: 1 };

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener('fetch', function (event) {
    var request = event.request;
    if (request.headers.get('X-Offline-Replay')) return;
    if (!DB.isQueueable(request.method, request.url)) return;
    event.respondWith(sendOrQueue(request));
});

self.addEventListener('sync', function (event) {
    if (event.tag === 'rm-offline-sync') event.waitUntil(replayFromWorker());
});

self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'replay') event.waitUntil(replayFromWorker());
});

function replayFromWorker() {
    return DB.getMeta('session').then(function (session) {
        if (!session) return null;
        return DB.replayAll({ userId: session.userId || '', csrfToken: session.csrfToken || '' });
    });
}

function pickHeaders(headers) {
    var kept = {};
    ['content-type', 'accept', 'x-requested-with'].forEach(function (name) {
        var value = headers.get(name);
        if (value) kept[name] = value;
    });
    return kept;
}

function sendOrQueue(request) {
    var isNavigation = request.mode === 'navigate';
    return request.clone().blob().then(function (body) {
        if (body.size > DB.MAX_BODY_BYTES) return fetch(request);
        var key = DB.newKey();
        var headers = new Headers(request.headers);
        headers.set('X-Idempotency-Key', key);
        var outgoing = new Request(request.url, {
            method: request.method,
            headers: headers,
            body: body.size ? body : null,
            credentials: 'same-origin',
            redirect: isNavigation ? 'manual' : request.redirect,
            referrer: request.referrer || 'about:client',
            referrerPolicy: request.referrerPolicy,
            cache: 'no-store',
        });
        return fetch(outgoing).then(function (response) {
            if (SERVER_DOWN[response.status] || response.headers.get('X-Regi-Retryable')) {
                return queue(request, body, key, 'server').catch(function () { return response; });
            }
            return response;
        }, function (error) {
            return queue(request, body, key, 'offline').catch(function () { throw error; });
        });
    }, function () {
        return fetch(request);
    });
}

function queue(request, body, key, reason) {
    return DB.getMeta('session').then(function (session) {
        session = session || {};
        var item = {
            key: key,
            url: request.url,
            method: request.method,
            headers: pickHeaders(request.headers),
            body: body.size ? body : null,
            kind: request.mode === 'navigate' ? 'form' : 'fetch',
            userId: session.userId || '',
            pageTitle: session.pageTitle || '',
            pageUrl: request.referrer || '',
            reason: reason,
            status: 'pending',
            attempts: 0,
            createdAt: Date.now(),
        };
        return DB.putItem(item).then(function () {
            DB.broadcast({ type: 'queued', key: key });
            if (self.registration.sync) self.registration.sync.register('rm-offline-sync').catch(function () {});
            return item.kind === 'form' ? savedPage(item) : savedJson(item);
        });
    });
}

function savedJson(item) {
    return new Response(JSON.stringify({
        ok: true,
        queued: true,
        offline: true,
        message: 'Saved on this device. It will be sent automatically when the connection is back.',
    }), { status: 202, headers: { 'Content-Type': 'application/json', 'X-Offline-Queued': '1' } });
}

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function savedPage(item) {
    var why = item.reason === 'offline' ? 'You appear to be offline.' : "The server isn't responding right now.";
    var back = item.pageUrl ? escapeHtml(item.pageUrl) : '/dashboard/';
    var html = '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        + '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<title>Saved offline · RegiManager</title><style>'
        + 'body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b1220;'
        + 'font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#e2e8f0;padding:1.5rem}'
        + '.card{max-width:480px;background:#111a2e;border:1px solid rgba(148,163,184,.18);border-radius:18px;padding:2rem;'
        + 'box-shadow:0 20px 60px rgba(0,0,0,.45)}'
        + '.icon{width:52px;height:52px;border-radius:14px;background:rgba(37,99,235,.18);display:flex;align-items:center;'
        + 'justify-content:center;font-size:26px;margin-bottom:1rem}'
        + 'h1{font-size:1.35rem;margin:0 0 .5rem}p{color:#94a3b8;line-height:1.6;margin:0 0 1rem}'
        + '.actions{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1.25rem}'
        + 'a,button{font:inherit;font-weight:600;border-radius:10px;padding:.7rem 1.2rem;cursor:pointer;text-decoration:none}'
        + '.primary{background:#2563eb;color:#fff;border:0}.ghost{background:transparent;color:#cbd5e1;border:1px solid rgba(148,163,184,.3)}'
        + '</style></head><body><div class="card"><div class="icon">&#9729;</div>'
        + '<h1>Saved on this device</h1>'
        + '<p>' + why + ' Your change was kept safely and will be sent to RegiManager automatically as soon as the connection is back. You don\'t need to submit it again.</p>'
        + '<p>Keep working; a "waiting to sync" badge shows at the bottom of the page until it\'s done.</p>'
        + '<div class="actions"><button class="primary" onclick="history.back()">Back to where I was</button>'
        + '<a class="ghost" href="' + back + '">Reload that page</a></div></div></body></html>';
    return new Response(html, { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', 'X-Offline-Queued': '1' } });
}
{% else %}
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.registration.unregister()); });
{% endif %}
