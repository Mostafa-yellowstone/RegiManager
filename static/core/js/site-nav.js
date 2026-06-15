(function () {
    if (window.__siteNavInit) return;
    window.__siteNavInit = true;

    function initSiteNav() {
        const mobileBtn = document.getElementById('siteMobileNavBtn');
        const mobileCloseBtn = document.getElementById('siteMobileNavClose');
        const mobileMenu = document.getElementById('siteMobileNav');
        const backdrop = document.getElementById('siteNavBackdrop');

        if (!mobileBtn || !mobileMenu) return;

        const closeMobileMenu = () => {
            mobileMenu.classList.remove('is-open');
            mobileMenu.setAttribute('aria-hidden', 'true');
            mobileBtn.setAttribute('aria-expanded', 'false');
            if (backdrop) {
                backdrop.classList.remove('is-visible');
                backdrop.hidden = true;
            }
            document.body.classList.remove('site-nav-open');
        };

        const openMobileMenu = () => {
            mobileMenu.classList.add('is-open');
            mobileMenu.setAttribute('aria-hidden', 'false');
            mobileBtn.setAttribute('aria-expanded', 'true');
            if (backdrop) {
                backdrop.classList.add('is-visible');
                backdrop.hidden = false;
            }
            document.body.classList.add('site-nav-open');
        };

        const toggleMobileMenu = () => {
            if (mobileMenu.classList.contains('is-open')) {
                closeMobileMenu();
            } else {
                openMobileMenu();
            }
        };

        mobileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleMobileMenu();
        });

        if (mobileCloseBtn) {
            mobileCloseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                closeMobileMenu();
            });
        }

        if (backdrop) {
            backdrop.addEventListener('click', closeMobileMenu);
        }

        mobileMenu.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', closeMobileMenu);
        });

        window.addEventListener('resize', () => {
            if (window.innerWidth > 1200) closeMobileMenu();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeMobileMenu();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSiteNav);
    } else {
        initSiteNav();
    }
})();
