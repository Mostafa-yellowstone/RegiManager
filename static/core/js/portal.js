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
                if (locDropdown) locDropdown.classList.remove('is-open');
                if (locDropdownDrawer) locDropdownDrawer.classList.remove('is-open');
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
                if (open) panel.classList.add('is-open');
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
                    if (open) locDropdownDrawer.classList.add('is-open');
                });
            }

            if (mobileBtn && mobileMenu) {
                mobileBtn.addEventListener('click', (e) => {
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

            window.addEventListener('resize', () => {
                if (window.innerWidth > 1200) closeMobileMenu();
            });

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
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => Portal.init());
    } else {
        Portal.init();
    }

    window.Portal = Portal;
})();
