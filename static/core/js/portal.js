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
            const soundUrl = body && body.getAttribute('data-notif-sound-url');
            if (!pollUrl) return;

            const STORAGE_KEY = 'regimanager_last_notif_id';
            const INIT_KEY = 'regimanager_notif_poller_ready';
            const PENDING_KEY = 'regimanager_pending_policy_alert';
            const CHANNEL_NAME = 'regimanager-notifications';
            const POLL_VISIBLE_MS = 5000;
            const POLL_HIDDEN_MS = 8000;

            let lastKnownId = 0;
            let pollTimer = null;
            let alertAudio = null;
            let audioReady = false;

            try {
                lastKnownId = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10) || 0;
            } catch (e) {
                lastKnownId = 0;
            }

            if (soundUrl) {
                alertAudio = new Audio(soundUrl);
                alertAudio.preload = 'auto';
                alertAudio.volume = 0.9;
            }

            const unlockAudio = () => {
                if (!alertAudio || audioReady) return;
                alertAudio.play().then(() => {
                    alertAudio.pause();
                    alertAudio.currentTime = 0;
                    audioReady = true;
                }).catch(() => {});
            };

            const playAssignmentChime = () => {
                if (!alertAudio) return;
                try {
                    alertAudio.currentTime = 0;
                    const playPromise = alertAudio.play();
                    if (playPromise && playPromise.catch) {
                        playPromise.catch(() => {});
                    }
                } catch (e) {}
            };

            const showEnableBanner = () => {
                const banner = document.getElementById('notifEnableBanner');
                if (!banner || !('Notification' in window)) return;
                if (Notification.permission === 'granted') {
                    banner.classList.add('is-hidden');
                    return;
                }
                banner.classList.remove('is-hidden');
            };

            const hideEnableBanner = () => {
                const banner = document.getElementById('notifEnableBanner');
                if (banner) banner.classList.add('is-hidden');
            };

            const showDesktopAlerts = (policyAlerts) => {
                if (!policyAlerts || !policyAlerts.length || !('Notification' in window)) return;
                if (Notification.permission !== 'granted') return;
                policyAlerts.forEach((notif) => {
                    try {
                        const desktop = new Notification(notif.title, {
                            body: `${notif.client_name}${notif.message ? ' • ' + notif.message : ''}`,
                            tag: `policy-notif-${notif.id}`,
                            requireInteraction: true,
                        });
                        desktop.onclick = () => {
                            window.focus();
                            window.location.href = notif.url;
                            desktop.close();
                        };
                    } catch (e) {}
                });
            };

            const markPendingPolicyAlert = () => {
                try {
                    sessionStorage.setItem(PENDING_KEY, '1');
                } catch (e) {}
            };

            const consumePendingPolicyAlert = () => {
                try {
                    if (sessionStorage.getItem(PENDING_KEY) === '1') {
                        sessionStorage.removeItem(PENDING_KEY);
                        return true;
                    }
                } catch (e) {}
                return false;
            };

            const requestDesktopPermission = async () => {
                if (!('Notification' in window)) return false;
                try {
                    const result = await Notification.requestPermission();
                    if (result === 'granted') {
                        hideEnableBanner();
                        unlockAudio();
                        return true;
                    }
                } catch (e) {}
                return false;
            };

            document.addEventListener('click', unlockAudio, { once: false });
            document.addEventListener('keydown', unlockAudio, { once: false });

            const enableBtn = document.getElementById('notifEnableBtn');
            const dismissBtn = document.getElementById('notifEnableDismiss');
            if (enableBtn) {
                enableBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await requestDesktopPermission();
                    unlockAudio();
                });
            }
            if (dismissBtn) {
                dismissBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    hideEnableBanner();
                });
            }
            showEnableBanner();

            let channel = null;
            try {
                if (typeof BroadcastChannel !== 'undefined') {
                    channel = new BroadcastChannel(CHANNEL_NAME);
                    channel.onmessage = (event) => {
                        if (!event.data) return;
                        if (event.data.type === 'new-notifications') {
                            this.renderNotifications(event.data.payload, {
                                playSound: !!event.data.playSound,
                                animate: true,
                            });
                        }
                    };
                }
            } catch (e) {}

            this.escapeHtml = (value) => {
                return String(value || '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;');
            };

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

            const handleIncomingPolicyAlerts = (payload, policyAlerts) => {
                if (!policyAlerts || !policyAlerts.length) return;

                this.renderNotifications(payload, { playSound: !document.hidden, animate: true });

                if (document.hidden) {
                    showDesktopAlerts(policyAlerts);
                    markPendingPolicyAlert();
                    if (channel) {
                        channel.postMessage({
                            type: 'new-notifications',
                            payload,
                            playSound: false,
                        });
                    }
                } else {
                    if (channel) {
                        channel.postMessage({
                            type: 'new-notifications',
                            payload,
                            playSound: true,
                        });
                    }
                }
            };

            const poll = async () => {
                try {
                    const url = `${pollUrl}?after_id=${encodeURIComponent(lastKnownId)}`;
                    const res = await fetch(url, {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'same-origin',
                        cache: 'no-store',
                    });
                    if (!res.ok) return;
                    const payload = await res.json();
                    const latestId = payload.latest_id || 0;
                    const policyAlerts = payload.new_policy_notifications || [];
                    let pollerReady = false;

                    try {
                        pollerReady = localStorage.getItem(INIT_KEY) === '1';
                    } catch (e) {
                        pollerReady = false;
                    }

                    if (!pollerReady) {
                        this.renderNotifications(payload, { playSound: false, animate: false });
                        if (latestId > lastKnownId) {
                            lastKnownId = latestId;
                            try {
                                localStorage.setItem(STORAGE_KEY, String(lastKnownId));
                                localStorage.setItem(INIT_KEY, '1');
                            } catch (e) {}
                        }
                        return;
                    }

                    if (policyAlerts.length > 0) {
                        handleIncomingPolicyAlerts(payload, policyAlerts);
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

            const schedulePoll = () => {
                if (pollTimer) clearInterval(pollTimer);
                const interval = document.hidden ? POLL_HIDDEN_MS : POLL_VISIBLE_MS;
                pollTimer = setInterval(poll, interval);
            };

            poll();
            schedulePoll();

            document.addEventListener('visibilitychange', () => {
                schedulePoll();
                poll();
                if (!document.hidden && consumePendingPolicyAlert()) {
                    playAssignmentChime();
                }
            });

            window.addEventListener('focus', () => {
                poll();
                if (consumePendingPolicyAlert()) {
                    playAssignmentChime();
                }
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
