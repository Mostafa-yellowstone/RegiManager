/**
 * 🎃 REGIMANAGER HALLOWEEN FESTIVAL JAVASCRIPT ENGINE
 * Handles spider silk descent, character badge Injection, theme switching, and spooky particle effects.
 */
(function () {
  'use strict';

  function initHalloweenEngine() {
    var isMasterEnabled = document.body.dataset.halloweenMaster !== 'false';
    var savedChoice = localStorage.getItem('rm_halloween_choice');

    // Default to active if master enabled, unless user explicitly turned off
    var isActive = isMasterEnabled && savedChoice !== 'off';

    if (isActive) {
      document.body.classList.add('halloween-active');
      injectSpiderDescent();
      injectCharacterBadges();
    }

    injectHeaderToggle(isActive);
  }

  function injectSpiderDescent() {
    if (document.getElementById('hw-spider-wrapper')) return;

    var wrapper = document.createElement('div');
    wrapper.id = 'hw-spider-wrapper';
    wrapper.className = 'active';

    wrapper.innerHTML = [
      '<div class="hw-silk-thread" id="hw-thread"></div>',
      '<svg class="hw-spider-body" id="hw-spider-svg" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">',
      '  <!-- Spider Legs -->',
      '  <path d="M50 45 C20 15, 10 35, 5 40 M50 45 C80 15, 90 35, 95 40" stroke="#a855f7" stroke-width="4" stroke-linecap="round"/>',
      '  <path d="M50 50 C15 30, 5 55, 2 65 M50 50 C85 30, 95 55, 98 65" stroke="#a855f7" stroke-width="4" stroke-linecap="round"/>',
      '  <path d="M50 55 C20 70, 10 85, 15 95 M50 55 C80 70, 90 85, 85 95" stroke="#a855f7" stroke-width="4" stroke-linecap="round"/>',
      '  <!-- Spider Body & Eyes -->',
      '  <ellipse cx="50" cy="40" rx="14" ry="12" fill="#140d24" stroke="#ff7518" stroke-width="3"/>',
      '  <circle cx="50" cy="65" r="20" fill="#0a0612" stroke="#a855f7" stroke-width="3"/>',
      '  <!-- Glowing Red/Yellow Eyes -->',
      '  <circle cx="44" cy="38" r="3" fill="#ff7518"/>',
      '  <circle cx="56" cy="38" r="3" fill="#ff7518"/>',
      '  <circle cx="48" cy="43" r="2" fill="#00ff66"/>',
      '  <circle cx="52" cy="43" r="2" fill="#00ff66"/>',
      '</svg>'
    ].join('');

    document.body.appendChild(wrapper);

    var thread = document.getElementById('hw-thread');
    var spiderSvg = document.getElementById('hw-spider-svg');

    // Smooth scroll silk thread extension
    window.addEventListener('scroll', function () {
      var scrollPos = window.scrollY || document.documentElement.scrollTop;
      var newHeight = Math.min(Math.max(100 + scrollPos * 0.4, 80), 450);
      if (thread) {
        thread.style.height = newHeight + 'px';
      }
    });

    // Click handler: Spider scuttles back to top with animation!
    if (spiderSvg) {
      spiderSvg.addEventListener('click', function () {
        spiderSvg.classList.add('hw-spider-scuttling');
        setTimeout(function () {
          spiderSvg.classList.remove('hw-spider-scuttling');
          if (thread) thread.style.height = '80px';
        }, 850);
      });
    }
  }

  function injectCharacterBadges() {
    // Inject character badges on Space headers or main navigation titles
    var pageText = document.body.innerText.toLowerCase();

    var spaceTitles = document.querySelectorAll('.space-header h1, .inventory-title, .dashboard-title, h1');
    spaceTitles.forEach(function (el) {
      if (el.dataset.hwBadged) return;
      var text = el.innerText.toLowerCase();
      var badge = null;

      if (text.includes('insurance') || text.includes('policy')) {
        badge = createBadge('hw-char-vampire', '🧛‍♂️ Vampire Count · Eternal Coverage');
      } else if (text.includes('dmv') || text.includes('vehicle') || text.includes('registration')) {
        badge = createBadge('hw-char-ghost', '👻 Ghost Rider · Spectral DMV');
      } else if (text.includes('defense') || text.includes('driving')) {
        badge = createBadge('hw-char-frankenstein', '🧟‍♂️ Frankenstein · Record Resurrector');
      } else if (text.includes('motorclub') || text.includes('roadside')) {
        badge = createBadge('hw-char-werewolf', '🐺 Night Werewolf · 24/7 Patrol');
      } else if (text.includes('staff') || text.includes('employee')) {
        badge = createBadge('hw-char-witch', '🧙‍♀️ Sorceress · Magic Workflows');
      }

      if (badge) {
        el.appendChild(badge);
        el.dataset.hwBadged = 'true';
      }
    });
  }

  function createBadge(cssClass, labelText) {
    var span = document.createElement('span');
    span.className = 'hw-char-badge ' + cssClass;
    span.style.marginLeft = '12px';
    span.style.verticalAlign = 'middle';
    span.innerText = labelText;
    return span;
  }

  function injectHeaderToggle(isActive) {
    var headerActions = document.querySelector('.nav-actions, .header-right, .user-menu');
    if (!headerActions || document.getElementById('hw-toggle-btn')) return;

    var btn = document.createElement('button');
    btn.id = 'hw-toggle-btn';
    btn.className = 'hw-toggle-btn';
    btn.type = 'button';
    btn.innerHTML = isActive ? '🎃 Halloween ON' : '👻 Halloween OFF';

    btn.addEventListener('click', function () {
      var currentlyActive = document.body.classList.contains('halloween-active');
      if (currentlyActive) {
        document.body.classList.remove('halloween-active');
        localStorage.setItem('rm_halloween_choice', 'off');
        btn.innerHTML = '👻 Halloween OFF';
        var spider = document.getElementById('hw-spider-wrapper');
        if (spider) spider.style.display = 'none';
      } else {
        document.body.classList.add('halloween-active');
        localStorage.setItem('rm_halloween_choice', 'on');
        btn.innerHTML = '🎃 Halloween ON';
        injectSpiderDescent();
        injectCharacterBadges();
        var spider = document.getElementById('hw-spider-wrapper');
        if (spider) spider.style.display = 'flex';
      }
    });

    headerActions.prepend(btn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHalloweenEngine);
  } else {
    initHalloweenEngine();
  }
})();
