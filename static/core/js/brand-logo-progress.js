/**
 * Global RegiManager brand logo progress loader.
 * Mirrors Pulse BrandLogoProgress: breathing logo + sweeping arc.
 * Shows while fetch/XHR requests and form submissions are in flight.
 */
(function () {
  'use strict';

  var SHOW_DELAY_MS = 160;
  var MIN_VISIBLE_MS = 280;
  var pending = 0;
  var showTimer = null;
  var shownAt = 0;
  var hideTimer = null;
  var root = null;
  var labelEl = null;

  var IGNORE_URL_PARTS = [
    'session-heartbeat',
    'set-portal-timezone',
    'favicon',
    // Background realtime — long-lived; must never drive the brand loader.
    '/api/portal/notifications/wait',
    '/api/portal/notifications/',
    '/api/portal/events/',
    '/api/portal/quote-pipeline/',
    '/api/portal/quote-distribution/',
  ];

  function ensureDom() {
    if (root) return root;
    root = document.getElementById('rmBrandLoader');
    if (!root) {
      root = document.createElement('div');
      root.id = 'rmBrandLoader';
      root.className = 'rm-brand-loader';
      root.setAttribute('aria-hidden', 'true');
      root.innerHTML =
        '<div class="rm-brand-loader__backdrop" aria-hidden="true"></div>' +
        '<div class="rm-brand-loader__topbar" aria-hidden="true"><div class="rm-brand-loader__topbar-fill"></div></div>' +
        '<div class="rm-brand-loader__card" role="status" aria-live="polite">' +
        '  <div class="rm-brand-loader__ring">' +
        '    <svg viewBox="0 0 100 100" aria-hidden="true">' +
        '      <circle class="rm-brand-loader__track" cx="50" cy="50" r="40"></circle>' +
        '      <circle class="rm-brand-loader__arc" cx="50" cy="50" r="40"></circle>' +
        '    </svg>' +
        '    <img class="rm-brand-loader__logo" alt="RegiManager" src="' + logoSrc() + '">' +
        '  </div>' +
        '  <p class="rm-brand-loader__label">Loading</p>' +
        '</div>';
      document.body.appendChild(root);
    }
    labelEl = root.querySelector('.rm-brand-loader__label');
    wireLogo(root.querySelector('.rm-brand-loader__logo'));
    return root;
  }

  function logoSrc() {
    var el = document.querySelector('[data-rm-brand-logo]');
    if (el && el.getAttribute('data-rm-brand-logo')) {
      return el.getAttribute('data-rm-brand-logo');
    }
    return '/static/core/img/logo_regimanager.png';
  }

  function logoFallback() {
    var el = document.querySelector('[data-rm-brand-logo-fallback]');
    if (el && el.getAttribute('data-rm-brand-logo-fallback')) {
      return el.getAttribute('data-rm-brand-logo-fallback');
    }
    return '/static/core/img/regimanager-logo-premium.png';
  }

  function wireLogo(img) {
    if (!img || img.dataset.rmLogoWired) return;
    img.dataset.rmLogoWired = '1';
    var primary = logoSrc();
    var fallback = logoFallback();
    img.setAttribute('data-fallback', fallback);
    img.addEventListener('error', function onLogoError() {
      if (fallback && img.src.indexOf(fallback) === -1) {
        img.src = fallback;
      }
    });
    if (!img.getAttribute('src')) {
      img.src = primary;
    }
  }

  function shouldIgnoreUrl(url) {
    if (!url) return false;
    var s = String(url).toLowerCase();
    for (var i = 0; i < IGNORE_URL_PARTS.length; i++) {
      if (s.indexOf(IGNORE_URL_PARTS[i]) !== -1) return true;
    }
    return false;
  }

  function reveal(label) {
    ensureDom();
    if (labelEl && label) labelEl.textContent = label;
    root.classList.add('is-visible');
    root.setAttribute('aria-hidden', 'false');
    shownAt = Date.now();
  }

  function conceal() {
    if (!root) return;
    root.classList.remove('is-visible');
    root.setAttribute('aria-hidden', 'true');
  }

  function begin(label) {
    pending += 1;
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (pending === 1 && !showTimer) {
      showTimer = setTimeout(function () {
        showTimer = null;
        if (pending > 0) reveal(label || 'Loading');
      }, SHOW_DELAY_MS);
    } else if (root && root.classList.contains('is-visible') && label && labelEl) {
      labelEl.textContent = label;
    }
  }

  function end() {
    pending = Math.max(0, pending - 1);
    if (pending > 0) return;

    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
      return;
    }

    var elapsed = Date.now() - shownAt;
    var wait = Math.max(0, MIN_VISIBLE_MS - elapsed);
    hideTimer = setTimeout(function () {
      hideTimer = null;
      if (pending === 0) conceal();
    }, wait);
  }

  function show(label, options) {
    options = options || {};
    ensureDom();
    root.classList.toggle('is-compact', !!options.compact);
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    pending = Math.max(pending, 1);
    reveal(label || 'Loading');
  }

  function hide() {
    pending = 0;
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    conceal();
  }

  function wrap(promise, label) {
    begin(label);
    return Promise.resolve(promise).finally(end);
  }

  function patchFetch() {
    if (!window.fetch || window.fetch.__rmBrandPatched) return;
    var nativeFetch = window.fetch.bind(window);
    function patchedFetch(input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (shouldIgnoreUrl(url)) {
        return nativeFetch(input, init);
      }
      begin('Loading');
      return nativeFetch(input, init).finally(end);
    }
    patchedFetch.__rmBrandPatched = true;
    window.fetch = patchedFetch;
  }

  function patchXhr() {
    if (!window.XMLHttpRequest || XMLHttpRequest.prototype.__rmBrandPatched) return;
    var open = XMLHttpRequest.prototype.open;
    var send = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__rmBrandUrl = url;
      return open.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      if (shouldIgnoreUrl(xhr.__rmBrandUrl)) {
        return send.apply(xhr, arguments);
      }
      var finished = false;
      function done() {
        if (finished) return;
        finished = true;
        end();
      }
      begin('Loading');
      xhr.addEventListener('loadend', done);
      xhr.addEventListener('abort', done);
      try {
        return send.apply(xhr, arguments);
      } catch (e) {
        done();
        throw e;
      }
    };
    XMLHttpRequest.prototype.__rmBrandPatched = true;
  }

  function initForms() {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;
      if (e.defaultPrevented) return;
      if (form.hasAttribute('data-rm-loader-skip')) return;
      if (form.getAttribute('target') === '_blank') return;
      begin(form.getAttribute('data-rm-loader-label') || 'Saving');
    });

    window.addEventListener('pageshow', function () {
      hide();
    });
  }

  function boot() {
    ensureDom();
    patchFetch();
    patchXhr();
    initForms();
  }

  window.RegiBrandLoader = {
    show: show,
    hide: hide,
    begin: begin,
    end: end,
    wrap: wrap,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
