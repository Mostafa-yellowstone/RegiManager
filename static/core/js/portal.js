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
