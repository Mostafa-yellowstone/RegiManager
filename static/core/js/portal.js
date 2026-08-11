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
            this.initTimezone();
            this.initTopNav();
            this.initTabs();
            this.initFilterPanels();
            this.initModals();
            this.initSiteNewsAlert();
            this.preserveCrmFilters();
            this.initRealtime();
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

        initTimezone() {
            let browserTz = '';
            try {
                browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
            } catch (e) {
                return;
            }
            if (!browserTz) return;

            const storageKey = 'portal_timezone_synced';
            try {
                if (sessionStorage.getItem(storageKey) === browserTz) {
                    return;
                }
            } catch (e) {}

            fetch('/api/set-portal-timezone/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken(),
                },
                body: JSON.stringify({ timezone: browserTz }),
                credentials: 'same-origin',
            })
                .then((res) => (res.ok ? res.json() : null))
                .then((data) => {
                    if (!data || data.status !== 'ok') return;
                    const reloadKey = storageKey + '_applied';
                    let needsReload = false;
                    try {
                        needsReload = !sessionStorage.getItem(reloadKey);
                        sessionStorage.setItem(storageKey, browserTz);
                    } catch (e) {}
                    const badge = document.getElementById('portalTimezoneBadge');
                    if (badge && data.label) {
                        badge.textContent = data.label;
                        badge.title = data.timezone;
                    }
                    if (needsReload) {
                        try {
                            sessionStorage.setItem(reloadKey, '1');
                        } catch (e) {}
                        window.location.reload();
                    }
                })
                .catch(() => null);
        },

        initTopNav() {
            const notifBtn = document.getElementById('notifBtn');
            const notifDropdown = document.getElementById('notifDropdown');
            const locBtn = document.getElementById('locBtn');
            const locDropdown = document.getElementById('locDropdown');
            const locBtnDrawer = document.getElementById('locBtnDrawer');
            const locDropdownDrawer = document.getElementById('locDropdownDrawer');
            const mobileBtn = document.getElementById('portalMobileNavBtn');
            const mobileCloseBtn = document.getElementById('portalMobileNavClose');
            const mobileMenu = document.getElementById('portalMobileNav');
            const backdrop = document.getElementById('portalNavBackdrop');
            const themeBtnDrawer = document.getElementById('portalThemeToggleDrawer');

            const closeMobileMenu = () => {
                if (!mobileMenu) return;
                mobileMenu.classList.remove('is-open');
                mobileMenu.setAttribute('aria-hidden', 'true');
                if (mobileBtn) mobileBtn.setAttribute('aria-expanded', 'false');
                if (backdrop) {
                    backdrop.classList.remove('is-visible');
                    backdrop.hidden = true;
                }
                document.body.classList.remove('portal-nav-open');
            };

            const openMobileMenu = () => {
                if (!mobileMenu) return;
                if (notifDropdown) notifDropdown.classList.remove('is-open');
                if (locDropdown) locDropdown.classList.remove('is-open');
                if (locDropdownDrawer) locDropdownDrawer.classList.remove('is-open');
                mobileMenu.classList.add('is-open');
                mobileMenu.setAttribute('aria-hidden', 'false');
                if (mobileBtn) mobileBtn.setAttribute('aria-expanded', 'true');
                if (backdrop) {
                    backdrop.classList.add('is-visible');
                    backdrop.hidden = false;
                }
                document.body.classList.add('portal-nav-open');
            };

            const closeDropdowns = () => {
                if (notifDropdown) notifDropdown.classList.remove('is-open');
                if (notifBtn) notifBtn.setAttribute('aria-expanded', 'false');
                if (locDropdown) locDropdown.classList.remove('is-open');
                if (locBtn) locBtn.setAttribute('aria-expanded', 'false');
                if (locDropdownDrawer) locDropdownDrawer.classList.remove('is-open');
                if (locBtnDrawer) locBtnDrawer.setAttribute('aria-expanded', 'false');
            };

            const closeAll = () => {
                closeDropdowns();
                closeMobileMenu();
            };

            const togglePanel = (btn, panel, { closesMobile = true } = {}) => {
                if (!btn || !panel) return;
                const open = !panel.classList.contains('is-open');
                closeDropdowns();
                if (closesMobile) closeMobileMenu();
                if (open) {
                    panel.classList.add('is-open');
                }
                if (btn.hasAttribute('aria-expanded')) {
                    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
                }
            };

            const toggleMobileMenu = () => {
                if (!mobileMenu) return;
                if (mobileMenu.classList.contains('is-open')) {
                    closeMobileMenu();
                } else {
                    openMobileMenu();
                }
            };

            if (notifBtn && notifDropdown) {
                notifBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePanel(notifBtn, notifDropdown);
                });
                this.initNotificationActions(notifDropdown);
            }

            if (locBtn && locDropdown) {
                locBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePanel(locBtn, locDropdown);
                });
            }

            if (locBtnDrawer && locDropdownDrawer) {
                locBtnDrawer.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const open = !locDropdownDrawer.classList.contains('is-open');
                    closeDropdowns();
                    if (open) {
                        locDropdownDrawer.classList.add('is-open');
                        locBtnDrawer.setAttribute('aria-expanded', 'true');
                    }
                });
            }

            if (mobileBtn && mobileMenu) {
                mobileBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleMobileMenu();
                });
            }

            if (mobileCloseBtn) {
                mobileCloseBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeMobileMenu();
                });
            }

            if (backdrop) {
                backdrop.addEventListener('click', closeMobileMenu);
            }

            if (themeBtnDrawer) {
                themeBtnDrawer.addEventListener('click', () => {
                    const mainThemeBtn = document.getElementById('portalThemeToggle');
                    if (mainThemeBtn) {
                        mainThemeBtn.click();
                    }
                });
            }

            mobileMenu?.querySelectorAll('a.nav-link').forEach((link) => {
                link.addEventListener('click', closeMobileMenu);
            });

            const topNav = document.querySelector('.top-nav');
            const navMenu = topNav ? topNav.querySelector('.nav-menu') : null;
            let navFitFrame = 0;

            const syncNavFit = () => {
                if (!topNav || !navMenu) return;
                const drawerOpen = !!(mobileMenu && mobileMenu.classList.contains('is-open'));
                // Don't tear down an open drawer while measuring.
                if (drawerOpen) return;

                topNav.classList.remove('top-nav--force-drawer');
                const menuStyle = window.getComputedStyle(navMenu);
                // CSS already in drawer mode (≤1400px) — leave button/drawer alone.
                if (menuStyle.display === 'none') return;

                const overflowing = navMenu.scrollWidth > navMenu.clientWidth + 1;
                const bar = topNav.querySelector('.top-nav__bar');
                const barOverflow = bar ? bar.scrollWidth > bar.clientWidth + 2 : false;
                if (overflowing || barOverflow) {
                    topNav.classList.add('top-nav--force-drawer');
                }
            };

            const scheduleNavFit = () => {
                if (navFitFrame) window.cancelAnimationFrame(navFitFrame);
                navFitFrame = window.requestAnimationFrame(() => {
                    navFitFrame = 0;
                    syncNavFit();
                });
            };

            scheduleNavFit();
            window.addEventListener('resize', () => {
                scheduleNavFit();
                if (window.innerWidth > 1400 && !topNav?.classList.contains('top-nav--force-drawer')) {
                    closeMobileMenu();
                }
            });
            if (window.visualViewport) {
                window.visualViewport.addEventListener('resize', scheduleNavFit);
            }

            document.addEventListener('click', (e) => {
                if (e.target.closest('#notifBtn, #notifDropdown, #locBtn, #locDropdown, #locBtnDrawer, #locDropdownDrawer, #portalMobileNavBtn, .portal-mobile-drawer, #portalNavBackdrop')) {
                    return;
                }
                closeAll();
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeAll();
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

        getCsrfToken() {
            const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
            return match ? decodeURIComponent(match[1]) : '';
        },

        updateNewsBadges(count) {
            document.querySelectorAll('.nav-news-badge').forEach((badge) => {
                if (count > 0) {
                    badge.textContent = String(count);
                    badge.hidden = false;
                } else {
                    badge.remove();
                }
            });
        },

        updateNotifBadges(count) {
            const pill = document.getElementById('notifCountPill');
            if (pill) {
                pill.textContent = `${count} unread`;
            }
            const btn = document.getElementById('notifBtn');
            if (!btn) return;
            let badge = btn.querySelector('.notif-badge');
            if (count > 0) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'notif-badge';
                    btn.appendChild(badge);
                }
                badge.textContent = String(count);
            } else if (badge) {
                badge.remove();
            }
            const markAll = document.getElementById('notifMarkAllReadBtn');
            if (markAll && count === 0) {
                markAll.remove();
            }
        },

        postNotifAction(url) {
            return fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
                credentials: 'same-origin',
            }).then((res) => (res.ok ? res.json() : null)).catch(() => null);
        },

        initNotificationActions(notifDropdown) {
            const markAllBtn = document.getElementById('notifMarkAllReadBtn');
            if (markAllBtn) {
                markAllBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const url = markAllBtn.dataset.url;
                    if (!url) return;
                    this.postNotifAction(url).then((data) => {
                        if (!data || !data.success) return;
                        notifDropdown.querySelectorAll('.notif-item-row').forEach((row) => row.remove());
                        const body = notifDropdown.querySelector('.notif-dropdown-body');
                        if (body && !body.querySelector('.notif-empty')) {
                            const empty = document.createElement('div');
                            empty.className = 'notif-empty';
                            empty.textContent = 'No notifications.';
                            body.appendChild(empty);
                        }
                        this.updateNotifBadges(0);
                    });
                });
            }

            notifDropdown.querySelectorAll('.notif-mark-one-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const url = btn.dataset.url;
                    const row = btn.closest('.notif-item-row');
                    if (!url) return;
                    this.postNotifAction(url).then((data) => {
                        if (!data || !data.success) return;
                        if (row) row.remove();
                        const body = notifDropdown.querySelector('.notif-dropdown-body');
                        if (body && !body.querySelector('.notif-item-row') && !body.querySelector('.notif-empty')) {
                            const empty = document.createElement('div');
                            empty.className = 'notif-empty';
                            empty.textContent = 'No notifications.';
                            body.appendChild(empty);
                        }
                        this.updateNotifBadges(
                            typeof data.unread_count === 'number' ? data.unread_count : 0
                        );
                    });
                });
            });
        },

        preserveCrmFilters() {
            const current = window.location.pathname + window.location.search;
            document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
                if (form.querySelector('input[name="next"]')) return;
                if (form.getAttribute('data-skip-next') === '1') return;
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'next';
                input.value = current;
                form.appendChild(input);
            });

            // Hero comparison form: keep advanced CRM filters when changing period.
            const compForm = document.getElementById('compForm');
            if (compForm) {
                const keepKeys = [
                    'q', 'stage', 'status', 'insurance_type', 'source', 'business_type',
                    'date_from', 'date_to', 'insurance_company', 'agent', 'min_premium', 'max_premium',
                    'bq', 'bank_account', 'bank_type', 'bank_category', 'bank_company',
                    'bank_date_from', 'bank_date_to', 'bank_min_amount', 'bank_max_amount',
                ];
                const params = new URLSearchParams(window.location.search);
                keepKeys.forEach((key) => {
                    const value = params.get(key);
                    if (value === null || value === '') return;
                    if (compForm.querySelector(`[name="${key}"]`)) return;
                    const hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = key;
                    hidden.value = value;
                    compForm.appendChild(hidden);
                });
            }
        },

        initSiteNewsAlert() {
            const modal = document.getElementById('siteNewsAlertModal');
            if (!modal) return;

            const newsId = modal.dataset.newsId;
            const markUrl = modal.dataset.markUrl;
            if (!newsId || !markUrl) return;

            const storageKey = `portal-news-dismissed-${newsId}`;
            try {
                if (sessionStorage.getItem(storageKey) === '1') return;
            } catch (e) {}

            const open = () => {
                modal.classList.add('is-open');
                document.body.classList.add('portal-modal-open');
            };

            const close = () => {
                modal.classList.remove('is-open');
                document.body.classList.remove('portal-modal-open');
            };

            const markRead = () => {
                const body = new URLSearchParams({ news_id: newsId });
                return fetch(markUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': this.getCsrfToken(),
                    },
                    body: body.toString(),
                    credentials: 'same-origin',
                })
                    .then((res) => (res.ok ? res.json() : null))
                    .catch(() => null);
            };

            const dismiss = (markAsRead) => {
                try {
                    sessionStorage.setItem(storageKey, '1');
                } catch (e) {}
                close();
                if (!markAsRead) return;
                markRead().then((data) => {
                    if (data && typeof data.unread_count === 'number') {
                        this.updateNewsBadges(data.unread_count);
                        if (data.unread_count > 0) {
                            window.location.reload();
                        }
                    }
                });
            };

            modal.querySelectorAll('[data-site-news-got-it]').forEach((btn) => {
                btn.addEventListener('click', () => dismiss(true));
            });
            modal.querySelectorAll('[data-site-news-dismiss]').forEach((el) => {
                el.addEventListener('click', () => dismiss(true));
            });

            open();
        },

        initRealtime() {
            const wrap = document.querySelector('.notif-wrap');
            const eventsUrl = wrap && wrap.dataset.eventsUrl;
            if (!eventsUrl || typeof window.EventSource === 'undefined') return;

            const root = document.getElementById('quotePipelineRoot');
            const orgId = root && root.dataset.orgId;
            let url = eventsUrl;
            if (orgId) {
                url += (url.indexOf('?') >= 0 ? '&' : '?') + 'org=' + encodeURIComponent(orgId);
            }

            let refreshTimer = null;
            const schedulePipelineRefresh = () => {
                if (!root) return;
                if (refreshTimer) clearTimeout(refreshTimer);
                refreshTimer = setTimeout(() => this.refreshQuotePipeline(), 350);
            };

            const connect = () => {
                const es = new EventSource(url, { withCredentials: true });
                es.addEventListener('notification.created', (ev) => {
                    try {
                        const data = JSON.parse(ev.data || '{}');
                        const payload = data.payload || data;
                        this.prependNotification(payload);
                        if (typeof payload.unread_count === 'number') {
                            this.updateNotifBadges(payload.unread_count);
                        }
                    } catch (e) {}
                });
                es.addEventListener('quote_pipeline.changed', () => {
                    schedulePipelineRefresh();
                });
                es.onerror = () => {
                    es.close();
                    setTimeout(connect, 4000);
                };
                this._eventSource = es;
            };
            connect();

            // Catch anything missed while the stream was down.
            this.refreshNotificationsSnapshot();
        },

        refreshNotificationsSnapshot() {
            const wrap = document.querySelector('.notif-wrap');
            const url = wrap && wrap.dataset.notifSnapshotUrl;
            if (!url) return;
            fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then((res) => (res.ok ? res.json() : null))
                .then((data) => {
                    if (!data) return;
                    if (typeof data.unread_count === 'number') {
                        this.updateNotifBadges(data.unread_count);
                    }
                    if (Array.isArray(data.notifications)) {
                        this.replaceNotificationList(data.notifications);
                    }
                })
                .catch(() => null);
        },

        refreshQuotePipeline() {
            const root = document.getElementById('quotePipelineRoot');
            if (!root) return;
            const url = root.dataset.snapshotUrl;
            if (!url) return;
            fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then((res) => (res.ok ? res.json() : null))
                .then((data) => {
                    if (!data || !data.html) return;
                    const live = root.querySelector('#iqpLiveRegion');
                    if (!live) return;
                    const holder = document.createElement('div');
                    holder.innerHTML = data.html;
                    const next = holder.querySelector('#iqpLiveRegion') || holder.firstElementChild;
                    if (next) live.replaceWith(next);
                })
                .catch(() => null);
        },

        replaceNotificationList(items) {
            const body = document.querySelector('#notifDropdown .notif-dropdown-body');
            if (!body) return;
            body.innerHTML = '';
            if (!items.length) {
                const empty = document.createElement('div');
                empty.className = 'notif-empty';
                empty.textContent = 'No notifications.';
                body.appendChild(empty);
                return;
            }
            items.slice(0, 12).forEach((item) => {
                body.appendChild(this.buildNotifRow(item));
            });
            this.bindMarkOneButtons(body);
        },

        prependNotification(item) {
            if (!item || !item.id) return;
            const body = document.querySelector('#notifDropdown .notif-dropdown-body');
            if (!body) return;
            const existing = body.querySelector('[data-notif-id="' + item.id + '"]');
            if (existing) return;
            const empty = body.querySelector('.notif-empty');
            if (empty) empty.remove();
            const row = this.buildNotifRow(item);
            body.insertBefore(row, body.firstChild);
            this.bindMarkOneButtons(row);
            const markAll = document.getElementById('notifMarkAllReadBtn');
            if (markAll) markAll.style.display = '';
        },

        buildNotifRow(item) {
            const row = document.createElement('div');
            row.className = 'notif-item-row';
            row.dataset.notifId = String(item.id);
            const openUrl = item.open_url || ('/dashboard/notifications/' + item.id + '/open/');
            const levelClass = item.level === 'warning' ? 'warning' : 'info';
            const msg = (item.message || '').trim();
            const when = item.created_label || '';
            row.innerHTML =
                '<a href="' + openUrl + '" class="notif-item">' +
                '<div class="notif-item-inner">' +
                '<div class="notif-dot ' + levelClass + '"></div>' +
                '<div class="notif-item-body">' +
                '<div class="notif-item-title"></div>' +
                '<div class="notif-item-msg"></div>' +
                '<div class="notif-item-time"></div>' +
                '</div></div></a>' +
                '<button type="button" class="notif-action-btn notif-mark-one-btn" title="Mark as read" aria-label="Mark notification as read" data-url="/dashboard/notifications/' + item.id + '/read/">' +
                '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>' +
                '</button>';
            row.querySelector('.notif-item-title').textContent = item.title || 'Notification';
            row.querySelector('.notif-item-msg').textContent = msg ? ('System • ' + msg) : 'System';
            row.querySelector('.notif-item-time').textContent = when;
            return row;
        },

        bindMarkOneButtons(scope) {
            const root = scope || document;
            root.querySelectorAll('.notif-mark-one-btn').forEach((btn) => {
                if (btn.dataset.bound === '1') return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const url = btn.dataset.url;
                    const row = btn.closest('.notif-item-row');
                    if (!url) return;
                    this.postNotifAction(url).then((data) => {
                        if (!data || !data.success) return;
                        if (row) row.remove();
                        const body = document.querySelector('#notifDropdown .notif-dropdown-body');
                        if (body && !body.querySelector('.notif-item-row') && !body.querySelector('.notif-empty')) {
                            const empty = document.createElement('div');
                            empty.className = 'notif-empty';
                            empty.textContent = 'No notifications.';
                            body.appendChild(empty);
                        }
                        this.updateNotifBadges(
                            typeof data.unread_count === 'number' ? data.unread_count : 0
                        );
                    });
                });
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
