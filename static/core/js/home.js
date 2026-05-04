(function () {
    const accountMenu = document.querySelector("[data-account-menu]");
    const accountTrigger = document.querySelector("[data-account-trigger]");
    const languageMenu = document.querySelector("[data-language-menu]");
    const languageTrigger = document.querySelector("[data-language-trigger]");
    const navToggle = document.querySelector("[data-nav-toggle]");
    const siteNav = document.querySelector("[data-site-nav]");
    const siteHeader = document.querySelector(".site-header");
    const revealItems = document.querySelectorAll(".reveal");
    const tiltCard = document.querySelector("[data-tilt]");
    const cursorGlow = document.querySelector("[data-cursor-glow]");
    const pageLoader = document.querySelector("[data-page-loader]");
    const orb = document.querySelector("[data-float-orb]");

    const closeMenus = function () {
        if (accountMenu) {
            accountMenu.classList.remove("open");
            accountTrigger.setAttribute("aria-expanded", "false");
        }
        if (languageMenu) {
            languageMenu.classList.remove("open");
            languageTrigger.setAttribute("aria-expanded", "false");
        }
    };

    if (accountMenu && accountTrigger) {
        accountTrigger.addEventListener("click", function (e) {
            e.stopPropagation();
            const isOpen = accountMenu.classList.toggle("open");
            accountTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
            if (isOpen && languageMenu) {
                languageMenu.classList.remove("open");
                languageTrigger.setAttribute("aria-expanded", "false");
            }
        });
    }

    if (languageMenu && languageTrigger) {
        languageTrigger.addEventListener("click", function (e) {
            e.stopPropagation();
            const isOpen = languageMenu.classList.toggle("open");
            languageTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
            if (isOpen && accountMenu) {
                accountMenu.classList.remove("open");
                accountTrigger.setAttribute("aria-expanded", "false");
            }
        });

        // Language selection logic
        const langOptions = languageMenu.querySelectorAll(".lang-option");
        const langForm = document.getElementById("lang-form");
        const langInput = document.getElementById("lang-input");

        langOptions.forEach(function (option) {
            option.addEventListener("click", function (e) {
                e.preventDefault();
                const langCode = this.getAttribute("data-lang");
                if (langForm && langInput) {
                    langInput.value = langCode;
                    langForm.submit();
                }
            });
        });
    }

    document.addEventListener("click", function (event) {
        closeMenus();
    });

    if (navToggle && siteNav) {
        navToggle.addEventListener("click", function () {
            const isOpen = siteNav.classList.toggle("open");
            navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });
    }

    // Smooth scroll with centering
    const navLinks = document.querySelectorAll(".site-nav a");
    navLinks.forEach(function (link) {
        link.addEventListener("click", function (e) {
            const href = this.getAttribute("href");
            if (!href.startsWith("#")) return;
            
            e.preventDefault();
            const targetId = href.substring(1);
            const targetElement = document.getElementById(targetId);
            
            if (targetElement) {
                if (siteNav.classList.contains("open")) {
                    siteNav.classList.remove("open");
                    navToggle.setAttribute("aria-expanded", "false");
                }

                const elementRect = targetElement.getBoundingClientRect();
                const absoluteElementTop = elementRect.top + window.pageYOffset;
                const viewportHeight = window.innerHeight;
                const elementHeight = targetElement.offsetHeight;
                
                // Calculate position to center the element
                let scrollToPosition = absoluteElementTop - (viewportHeight / 2) + (elementHeight / 2);
                
                // Ensure we don't scroll above the page top
                scrollToPosition = Math.max(0, scrollToPosition);
                
                window.scrollTo({
                    top: scrollToPosition,
                    behavior: "smooth"
                });

                // Update URL hash without jumping
                history.pushState(null, null, href);
            }
        });
    });

    const applyHeaderState = function () {
        if (!siteHeader) {
            return;
        }
        if (window.scrollY > 24) {
            siteHeader.classList.add("scrolled");
        } else {
            siteHeader.classList.remove("scrolled");
        }
    };

    applyHeaderState();
    window.addEventListener("scroll", applyHeaderState, { passive: true });

    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("visible");
                        revealObserver.unobserve(entry.target);
                    }
                });
            },
            {
                threshold: 0.16,
                rootMargin: "0px 0px -6% 0px",
            }
        );

        revealItems.forEach(function (item) {
            revealObserver.observe(item);
        });
    } else {
        revealItems.forEach(function (item) {
            item.classList.add("visible");
        });
    }

    const clamp = function (value, min, max) {
        return Math.min(Math.max(value, min), max);
    };

    let rafId = 0;
    const pointerState = {
        x: window.innerWidth / 2,
        y: window.innerHeight / 2,
    };

    const updatePointerEffects = function () {
        rafId = 0;
        const nx = pointerState.x / window.innerWidth - 0.5;
        const ny = pointerState.y / window.innerHeight - 0.5;

        if (tiltCard) {
            const rx = clamp(ny * -7, -7, 7);
            const ry = clamp(nx * 9, -9, 9);
            tiltCard.style.transform = "rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg)";
        }

        if (orb) {
            const ox = clamp(nx * 12, -12, 12);
            const oy = clamp(ny * 12, -12, 12);
            orb.style.transform = "translate3d(" + ox.toFixed(2) + "px," + oy.toFixed(2) + "px,0)";
        }

        if (cursorGlow) {
            cursorGlow.style.left = pointerState.x + "px";
            cursorGlow.style.top = pointerState.y + "px";
        }
    };

    window.addEventListener(
        "mousemove",
        function (event) {
            pointerState.x = event.clientX;
            pointerState.y = event.clientY;
            if (cursorGlow) {
                cursorGlow.style.opacity = "1";
            }
            if (!rafId) {
                rafId = requestAnimationFrame(updatePointerEffects);
            }
        },
        { passive: true }
    );

    document.addEventListener("mouseleave", function () {
        if (cursorGlow) {
            cursorGlow.style.opacity = "0";
        }
    });

    window.addEventListener("load", function () {
        if (pageLoader) {
            window.setTimeout(function () {
                pageLoader.classList.add("hidden");
            }, 180);
        }
    });
})();
