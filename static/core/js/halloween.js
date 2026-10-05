/**
 * 🎃 REGIMANAGER ULTRA-SCARY HALLOWEEN FESTIVAL JAVASCRIPT ENGINE
 * Handles corner cobwebs, flying bats & specters, rising pumpkin embers,
 * spider descent, character badges, and per-PSB theme switching.
 */
(function () {
  'use strict';

  function initHalloweenEngine() {
    var isActive = document.body.dataset.halloweenMaster !== 'false';

    if (isActive) {
      document.body.classList.add('halloween-active');
      injectCornerCobwebs();
      injectParticles();
      injectSpiderDescent();
      injectCharacterBadges();
    }
  }

  function injectCornerCobwebs() {
    if (document.getElementById('hw-cobweb-left')) return;

    var svgCobweb = [
      '<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">',
      '  <path d="M0 0 L100 0 L0 100 Z" fill="rgba(168,85,247,0.05)"/>',
      '  <path d="M0 0 L100 0 M0 0 L85 30 M0 0 L65 65 M0 0 L30 85 M0 0 L0 100" stroke="#a855f7" stroke-width="1.5" stroke-linecap="round"/>',
      '  <path d="M20 0 Q25 12 0 20 M40 0 Q48 24 0 40 M60 0 Q72 36 0 60 M80 0 Q94 48 0 80" stroke="#ff7518" stroke-width="1" fill="none"/>',
      '  <path d="M30 0 Q38 18 0 30 M50 0 Q62 30 0 50 M70 0 Q84 42 0 70" stroke="#a855f7" stroke-width="1" fill="none"/>',
      '</svg>'
    ].join('');

    var leftWeb = document.createElement('div');
    leftWeb.id = 'hw-cobweb-left';
    leftWeb.className = 'hw-cobweb-corner-left';
    leftWeb.innerHTML = svgCobweb;

    var rightWeb = document.createElement('div');
    rightWeb.id = 'hw-cobweb-right';
    rightWeb.className = 'hw-cobweb-corner-right';
    rightWeb.innerHTML = svgCobweb;

    document.body.appendChild(leftWeb);
    document.body.appendChild(rightWeb);
  }

  function injectParticles() {
    if (document.getElementById('hw-particle-layer')) return;

    var layer = document.createElement('div');
    layer.id = 'hw-particle-layer';
    layer.className = 'hw-particle-layer';

    // 🦇 Flying Bats
    for (var b = 0; b < 3; b++) {
      var bat = document.createElement('div');
      bat.className = 'hw-bat';
      bat.style.animationDelay = (b * 4.5) + 's';
      bat.innerHTML = '<svg viewBox="0 0 64 32" fill="#a855f7"><path d="M32 16 C24 0 8 4 0 16 C10 16 18 24 32 32 C46 24 54 16 64 16 C56 4 40 0 32 16 Z"/></svg>';
      layer.appendChild(bat);
    }

    // 👻 Floating Ghost Specter
    for (var g = 0; g < 2; g++) {
      var ghost = document.createElement('div');
      ghost.className = 'hw-ghost-specter';
      ghost.style.animationDelay = (g * 7) + 's';
      ghost.innerText = '👻';
      layer.appendChild(ghost);
    }

    // 🎃 Rising Pumpkin Embers
    for (var p = 0; p < 4; p++) {
      var pumpkin = document.createElement('div');
      pumpkin.className = 'hw-pumpkin-ember';
      pumpkin.style.left = (15 + p * 24) + 'vw';
      pumpkin.style.animationDelay = (p * 3.2) + 's';
      pumpkin.innerText = '🎃';
      layer.appendChild(pumpkin);
    }

    document.body.appendChild(layer);
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
      '  <!-- Spider Body & Glowing Red/Yellow Eyes -->',
      '  <ellipse cx="50" cy="40" rx="14" ry="12" fill="#140d24" stroke="#ff7518" stroke-width="3"/>',
      '  <circle cx="50" cy="65" r="20" fill="#0a0612" stroke="#a855f7" stroke-width="3"/>',
      '  <circle cx="44" cy="38" r="3.5" fill="#ff7518"/>',
      '  <circle cx="56" cy="38" r="3.5" fill="#ff7518"/>',
      '  <circle cx="48" cy="43" r="2.5" fill="#00ff66"/>',
      '  <circle cx="52" cy="43" r="2.5" fill="#00ff66"/>',
      '</svg>'
    ].join('');

    document.body.appendChild(wrapper);

    var thread = document.getElementById('hw-thread');
    var spiderSvg = document.getElementById('hw-spider-svg');

    window.addEventListener('scroll', function () {
      var scrollPos = window.scrollY || document.documentElement.scrollTop;
      var newHeight = Math.min(Math.max(120 + scrollPos * 0.45, 90), 500);
      if (thread) {
        thread.style.height = newHeight + 'px';
      }
    });

    if (spiderSvg) {
      spiderSvg.addEventListener('click', function () {
        spiderSvg.classList.add('hw-spider-scuttling');
        setTimeout(function () {
          spiderSvg.classList.remove('hw-spider-scuttling');
          if (thread) thread.style.height = '90px';
        }, 850);
      });
    }
  }

  function injectCharacterBadges() {
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHalloweenEngine);
  } else {
    initHalloweenEngine();
  }
})();
