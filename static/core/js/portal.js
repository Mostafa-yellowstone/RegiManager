/**
 * RegiManager Portal — authenticated workspace UI only.
 * Loaded via base_portal.html; never applied to public/marketing pages.
 */
(function () {
    'use strict';

    const THEME_KEY = 'portal-theme';

    const Portal = {
        init() {
            this.initTheme();
            this.initTopNav();
            this.initNotificationPoller();
            this.initTabs();
            this.initFilterPanels();
            this.initModals();
        },

        applyTheme(theme) {
            const isDark = theme === 'dark';
            document.documentElement.classList.toggle('portal-theme-dark', isDark);
            document.documentElement.setAttribute('data-portal-theme', theme);
            const btn = document.getElementById('portalThemeToggle');
            if (btn) {
                btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
                btn.title = isDark ? 'Light mode' : 'Dark mode';
            }
        },

        initTheme() {
            let theme = 'light';
            try {
                const stored = localStorage.getItem(THEME_KEY);
                if (stored === 'dark' || stored === 'light') {
                    theme = stored;
                } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    theme = 'dark';
                }
            } catch (e) {
                theme = 'light';
            }

            this.applyTheme(theme);

            const btn = document.getElementById('portalThemeToggle');
            if (!btn) return;

            btn.addEventListener('click', () => {
                const next = document.documentElement.classList.contains('portal-theme-dark') ? 'light' : 'dark';
                this.applyTheme(next);
                try {
                    localStorage.setItem(THEME_KEY, next);
                } catch (e) {}
            });
        },

        initTopNav() {
            const notifBtn = document.getElementById('notifBtn');
            const notifDropdown = document.getElementById('notifDropdown');
            const locBtn = document.getElementById('locBtn');
            const locDropdown = document.getElementById('locDropdown');
            const mobileBtn = document.getElementById('portalMobileNavBtn');
            const mobileMenu = document.getElementById('portalMobileNav');

            const closeAll = () => {
                if (notifDropdown) notifDropdown.classList.remove('is-open');
                if (locDropdown) locDropdown.classList.remove('is-open');
                if (mobileMenu) mobileMenu.classList.remove('is-open');
                if (mobileBtn) mobileBtn.setAttribute('aria-expanded', 'false');
            };

            const toggle = (btn, panel) => {
                if (!btn || !panel) return;
                const open = !panel.classList.contains('is-open');
                closeAll();
                if (open) {
                    panel.classList.add('is-open');
                    if (btn === mobileBtn) btn.setAttribute('aria-expanded', 'true');
                }
            };

            if (notifBtn && notifDropdown) {
                notifBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggle(notifBtn, notifDropdown);
                });
            }

            if (locBtn && locDropdown) {
                locBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggle(locBtn, locDropdown);
                });
            }

            if (mobileBtn && mobileMenu) {
                mobileBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggle(mobileBtn, mobileMenu);
                });
            }

            document.addEventListener('click', closeAll);
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeAll();
            });
        },

        initNotificationPoller() {
            const body = document.body;
            const pollUrl = body && body.getAttribute('data-notif-poll-url');
            if (!pollUrl) return;

            const POLL_MS = 15000;
            const STORAGE_KEY = 'regimanager_last_notif_id';
            const CHANNEL_NAME = 'regimanager-notifications';
            let lastKnownId = 0;
            let audioCtx = null;

            try {
                lastKnownId = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10) || 0;
            } catch (e) {
                lastKnownId = 0;
            }

            let channel = null;
            try {
                if (typeof BroadcastChannel !== 'undefined') {
                    channel = new BroadcastChannel(CHANNEL_NAME);
                    channel.onmessage = (event) => {
                        if (event.data && event.data.type === 'new-notifications') {
                            this.renderNotifications(event.data.payload, { playSound: false, animate: true });
                        }
                    };
                }
            } catch (e) {}

            const playAssignmentChime = () => {
                try {
                    const Ctx = window.AudioContext || window.webkitAudioContext;
                    if (!Ctx) return;
                    if (!audioCtx) audioCtx = new Ctx();
                    if (audioCtx.state === 'suspended') audioCtx.resume();

                    const now = audioCtx.currentTime;
                    const notes = [523.25, 659.25, 783.99];
                    notes.forEach((freq, i) => {
                        const osc = audioCtx.createOscillator();
                        const gain = audioCtx.createGain();
                        osc.type = 'sine';
                        osc.frequency.value = freq;
                        gain.gain.setValueAtTime(0.0001, now + i * 0.12);
                        gain.gain.exponentialRampToValueAtTime(0.18, now + i * 0.12 + 0.04);
                        gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.12 + 0.35);
                        osc.connect(gain);
                        gain.connect(audioCtx.destination);
                        osc.start(now + i * 0.12);
                        osc.stop(now + i * 0.12 + 0.4);
                    });
                } catch (e) {}
            };

            const maybeDesktopAlert = (payload) => {
                if (!document.hidden || !payload || !payload.notifications) return;
                const freshPolicy = payload.notifications.find((n) => n.is_policy);
                if (!freshPolicy || !('Notification' in window)) return;
                if (Notification.permission !== 'granted') return;
                try {
                    new Notification(freshPolicy.title, {
                        body: `${freshPolicy.client_name}${freshPolicy.message ? ' • ' + freshPolicy.message : ''}`,
                        tag: `policy-notif-${freshPolicy.id}`,
                    });
                } catch (e) {}
            };

            const requestDesktopPermission = () => {
                if (!('Notification' in window) || Notification.permission !== 'default') return;
                try {
                    Notification.requestPermission();
                } catch (e) {}
            };

            document.addEventListener('click', requestDesktopPermission, { once: true });

            this.renderNotifications = (payload, options = {}) => {
                const { playSound = false, animate = false } = options;
                const badge = document.getElementById('notifBadge');
                const countPill = document.getElementById('notifCountPill');
                const dropdownBody = document.getElementById('notifDropdownBody');
                const notifBtn = document.getElementById('notifBtn');
                const count = payload.unread_count || 0;

                if (badge) {
                    badge.textContent = count > 0 ? String(count) : '';
                    badge.classList.toggle('is-hidden', count <= 0);
                }
                if (countPill) {
                    countPill.textContent = `${count} unread`;
                }
                if (dropdownBody) {
                    if (!payload.notifications || !payload.notifications.length) {
                        dropdownBody.innerHTML = '<div class="notif-empty">No notifications.</div>';
                    } else {
                        dropdownBody.innerHTML = payload.notifications.map((n) => {
                            const levelClass = n.level === 'warning' ? 'warning' : (n.level === 'success' ? 'success' : 'info');
                            const msg = [n.client_name, n.message].filter(Boolean).join(' • ');
                            return `<a href="${n.url}" class="notif-item">
                                <div class="notif-item-inner">
                                    <div class="notif-dot ${levelClass}"></div>
                                    <div class="notif-item-body">
                                        <div class="notif-item-title">${this.escapeHtml(n.title)}</div>
                                        <div class="notif-item-msg">${this.escapeHtml(msg)}</div>
                                        <div class="notif-item-time">${this.escapeHtml(n.created_at)}</div>
                                    </div>
                                </div>
                            </a>`;
                        }).join('');
                    }
                }
                if (animate && notifBtn) {
                    notifBtn.classList.remove('has-new-alert');
                    void notifBtn.offsetWidth;
                    notifBtn.classList.add('has-new-alert');
                }
                if (playSound) playAssignmentChime();
            };

            this.escapeHtml = (value) => {
                return String(value || '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;');
            };

            const poll = async () => {
                try {
                    const res = await fetch(pollUrl, {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'same-origin',
                    });
                    if (!res.ok) return;
                    const payload = await res.json();
                    const latestId = payload.latest_id || 0;
                    const hasNew = latestId > lastKnownId;

                    if (hasNew && lastKnownId > 0) {
                        const hasPolicyAlert = (payload.notifications || []).some((n) => n.is_policy);
                        this.renderNotifications(payload, { playSound: hasPolicyAlert, animate: true });
                        maybeDesktopAlert(payload);
                        if (channel) {
                            channel.postMessage({ type: 'new-notifications', payload });
                        }
                    } else {
                        this.renderNotifications(payload, { playSound: false, animate: false });
                    }

                    if (latestId > lastKnownId) {
                        lastKnownId = latestId;
                        try {
                            localStorage.setItem(STORAGE_KEY, String(lastKnownId));
                        } catch (e) {}
                    }
                } catch (e) {}
            };

            poll();
            setInterval(poll, POLL_MS);
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) poll();
            });
        },

        initTabs() {
            document.querySelectorAll('[data-portal-tabs]').forEach((root) => {
                const buttons = root.querySelectorAll('[data-portal-tab]');
                const panels = root.querySelectorAll('[data-portal-tab-panel]');
                if (!buttons.length) return;

                const activate = (id) => {
                    buttons.forEach((btn) => {
                        const active = btn.dataset.portalTab === id;
                        btn.classList.toggle('is-active', active);
                        btn.setAttribute('aria-selected', active ? 'true' : 'false');
                    });
                    panels.forEach((panel) => {
                        panel.classList.toggle('is-active', panel.dataset.portalTabPanel === id);
                    });
                };

                buttons.forEach((btn) => {
                    btn.addEventListener('click', () => activate(btn.dataset.portalTab));
                });
            });
        },

        initFilterPanels() {
            document.querySelectorAll('[data-portal-filter-toggle]').forEach((btn) => {
                const targetId = btn.getAttribute('aria-controls');
                const panel = targetId ? document.getElementById(targetId) : null;
                if (!panel) return;

                btn.addEventListener('click', () => {
                    const open = panel.classList.toggle('is-open');
                    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
                });
            });
        },

        initModals() {
            document.querySelectorAll('[data-portal-modal-open]').forEach((trigger) => {
                const targetId = trigger.getAttribute('data-portal-modal-open');
                const modal = targetId ? document.getElementById(targetId) : null;
                if (!modal) return;

                const closeBtn = modal.querySelector('[data-portal-modal-close]');
                const backdrop = modal.querySelector('.portal-modal-backdrop');

                const open = () => {
                    modal.classList.add('is-open');
                    document.body.classList.add('portal-modal-open');
                };
                const close = () => {
                    modal.classList.remove('is-open');
                    document.body.classList.remove('portal-modal-open');
                };

                trigger.addEventListener('click', open);
                if (closeBtn) closeBtn.addEventListener('click', close);
                if (backdrop) backdrop.addEventListener('click', close);
            });
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => Portal.init());
    } else {
        Portal.init();
    }

    window.Portal = Portal;
})();
