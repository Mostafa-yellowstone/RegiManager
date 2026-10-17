/* RegiManager offline queue: page side (service worker registration, sync triggers, status badge). */
(function () {
    'use strict';

    var script = document.currentScript;
    var DB = window.RMOfflineDB;
    if (!script || !DB || !('serviceWorker' in navigator) || !window.indexedDB) return;

    var enabled = script.dataset.enabled === 'True';
    var swUrl = script.dataset.swUrl;
    var userId = script.dataset.userId || '';
    var retryTimer = null;
    var replaying = false;
    var badge = null;
    var pageId = DB.newKey();

    if (!enabled) {
        navigator.serviceWorker.getRegistrations().then(function (regs) {
            regs.forEach(function (reg) { reg.unregister(); });
        }).catch(function () {});
        return;
    }

    function csrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function describe(item) {
        var path = item.url;
        try { path = new URL(item.url).pathname; } catch (e) { /* keep url */ }
        var label = item.pageTitle ? item.pageTitle : path;
        return { label: label, path: path, when: new Date(item.createdAt).toLocaleString() };
    }

    function ensureBadge() {
        if (badge) return badge;
        badge = document.createElement('button');
        badge.type = 'button';
        badge.className = 'rm-offline-badge';
        badge.setAttribute('aria-live', 'polite');
        badge.hidden = true;
        badge.addEventListener('click', openPanel);
        document.body.appendChild(badge);
        return badge;
    }

    function setBadge(state, text) {
        var el = ensureBadge();
        el.className = 'rm-offline-badge rm-offline-badge--' + state;
        el.innerHTML = '<span class="rm-offline-dot"></span><span>' + escapeHtml(text) + '</span>';
        el.hidden = false;
    }

    function refreshBadge() {
        return DB.listItems(userId).then(function (items) {
            var waiting = items.filter(function (i) { return i.status === 'pending'; }).length;
            var needsAuth = items.filter(function (i) { return i.status === 'auth'; }).length;
            var problems = items.filter(function (i) { return i.status === 'failed' || i.status === 'review'; }).length;
            var offline = navigator.onLine === false;
            if (!items.length) {
                if (offline) setBadge('offline', "You're offline. Changes will be saved on this device.");
                else if (badge) badge.hidden = true;
                return items;
            }
            if (replaying) setBadge('syncing', 'Syncing ' + items.length + ' saved change' + (items.length > 1 ? 's' : '') + '…');
            else if (needsAuth) setBadge('auth', 'Sign in to finish syncing ' + (waiting + needsAuth) + ' change' + (waiting + needsAuth > 1 ? 's' : ''));
            else if (waiting) setBadge(offline ? 'offline' : 'pending', waiting + ' change' + (waiting > 1 ? 's' : '') + ' waiting to sync');
            else setBadge('problem', problems + ' saved change' + (problems > 1 ? 's need' : ' needs') + ' your attention');
            return items;
        }).catch(function () { return []; });
    }

    function scheduleRetry(ms) {
        clearTimeout(retryTimer);
        retryTimer = setTimeout(replay, Math.max(3000, ms || 20000));
    }

    function replay() {
        if (replaying || navigator.onLine === false) return refreshBadge();
        return DB.listItems(userId).then(function (items) {
            var due = items.filter(function (i) { return i.status === 'pending' || i.status === 'auth'; });
            if (!due.length) return refreshBadge();
            replaying = true;
            refreshBadge();
            return DB.replayAll({ userId: userId, csrfToken: csrfToken(), source: pageId }).then(function (summary) {
                replaying = false;
                if (!summary) return refreshBadge();
                if (summary.synced) notifySynced(summary);
                if (summary.waitMs) scheduleRetry(summary.waitMs);
                return refreshBadge();
            });
        }).catch(function () {
            replaying = false;
            scheduleRetry(30000);
            return refreshBadge();
        });
    }

    function notifySynced(summary) {
        var text = summary.synced + ' change' + (summary.synced > 1 ? 's' : '') + ' saved while offline ' + (summary.synced > 1 ? 'were' : 'was') + ' synced.';
        if (summary.failed || summary.review) text += ' Some need your attention; open the badge at the bottom of the page.';
        if (!window.Swal) return;
        Swal.fire({
            toast: true,
            position: 'bottom-end',
            icon: summary.failed || summary.review ? 'warning' : 'success',
            title: 'Back online',
            text: text,
            showConfirmButton: true,
            confirmButtonText: 'Refresh page',
            showCancelButton: true,
            cancelButtonText: 'Later',
            timer: 12000,
            timerProgressBar: true,
        }).then(function (result) {
            if (result.isConfirmed) window.location.reload();
        });
    }

    var STATUS_TEXT = {
        pending: 'Waiting to sync',
        auth: 'Waiting for you to sign in',
        failed: 'The server rejected this change',
        review: 'Sent. Please check the result (the form may have had errors)',
    };

    function openPanel() {
        DB.listItems(userId).then(function (items) {
            if (!window.Swal) return;
            var rows = items.map(function (item) {
                var d = describe(item);
                var status = STATUS_TEXT[item.status] || item.status;
                if (item.httpStatus) status += ' (HTTP ' + item.httpStatus + ')';
                var actions = '';
                if (item.status === 'failed' || item.status === 'review') {
                    actions = '<button type="button" class="rm-oq-act" data-act="retry" data-key="' + escapeHtml(item.key) + '">Retry</button>';
                    if (item.pageUrl) actions += '<a class="rm-oq-act" href="' + escapeHtml(item.pageUrl) + '">Open page</a>';
                }
                actions += '<button type="button" class="rm-oq-act rm-oq-danger" data-act="discard" data-key="' + escapeHtml(item.key) + '">Discard</button>';
                return '<li class="rm-oq-item rm-oq-' + escapeHtml(item.status) + '">'
                    + '<div class="rm-oq-title">' + escapeHtml(d.label) + '</div>'
                    + '<div class="rm-oq-meta">' + escapeHtml(item.method) + ' ' + escapeHtml(d.path) + ' · ' + escapeHtml(d.when) + '</div>'
                    + '<div class="rm-oq-status">' + escapeHtml(status) + '</div>'
                    + '<div class="rm-oq-actions">' + actions + '</div></li>';
            }).join('');
            var intro = navigator.onLine === false
                ? "You're offline. Anything you save is kept on this device and sent automatically when the connection returns."
                : 'These changes were saved while the connection or server was down.';
            Swal.fire({
                title: 'Changes saved offline',
                html: '<p class="rm-oq-intro">' + intro + '</p>' + (rows ? '<ul class="rm-oq-list">' + rows + '</ul>' : '<p>Nothing is waiting.</p>'),
                showConfirmButton: items.length > 0 && navigator.onLine !== false,
                confirmButtonText: 'Sync now',
                showCancelButton: true,
                cancelButtonText: 'Close',
                width: 640,
                didOpen: function (popup) {
                    popup.addEventListener('click', function (event) {
                        var btn = event.target.closest('[data-act]');
                        if (!btn) return;
                        var key = btn.getAttribute('data-key');
                        if (btn.getAttribute('data-act') === 'discard') {
                            if (!window.confirm('Discard this change? It will not be sent to the server.')) return;
                            DB.deleteItem(key).then(function () { Swal.close(); refreshBadge(); });
                        } else {
                            DB.getItem(key).then(function (item) {
                                if (!item) return;
                                item.status = 'pending';
                                return DB.putItem(item);
                            }).then(function () { Swal.close(); replay(); });
                        }
                    });
                },
            }).then(function (result) {
                if (result.isConfirmed) replay();
            });
        });
    }

    DB.setMeta('session', {
        userId: userId,
        csrfToken: csrfToken(),
        pageTitle: document.title,
        updatedAt: Date.now(),
    }).catch(function () {});

    navigator.serviceWorker.register(swUrl, { scope: '/' }).catch(function () {});

    try {
        var channel = new BroadcastChannel(DB.CHANNEL);
        channel.onmessage = function (event) {
            var msg = event.data || {};
            if (msg.type === 'queued') {
                refreshBadge();
                if (navigator.onLine !== false) scheduleRetry(15000);
            } else if (msg.type === 'changed') {
                if (msg.summary && msg.summary.synced && msg.summary.source !== pageId) notifySynced(msg.summary);
                refreshBadge();
            }
        };
    } catch (e) { /* BroadcastChannel unsupported */ }

    window.addEventListener('online', function () { setTimeout(replay, 1500); });
    window.addEventListener('offline', refreshBadge);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) replay(); });
    setInterval(function () { if (!document.hidden) replay(); }, 30000);

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(replay, 1200); });
    else setTimeout(replay, 1200);
})();
