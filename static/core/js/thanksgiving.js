/* =========================================================
   THANKSGIVING HARVEST THEME ENGINE — RegiManager
   High-performance SVG animations: falling autumn leaves,
   turkey mascot, wheat sheaves, per-PSB toggle with persistence
   ========================================================= */
(function () {
  'use strict';

  const STORAGE_KEY = 'rm_thanksgiving_choice';
  const MASTER_ENABLED = document.body.dataset.thanksgivingMaster === 'true';
  if (!MASTER_ENABLED) return;

  /* ── 5 Distinct SVG Autumn Leaf Shapes (Maple, Oak, Aspen, Elm, Scarlet) ── */
  const LEAF_SVGS = [
    // 1. Maple Leaf (Vibrant Red)
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 70" width="30" height="35" style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.15));">
      <path fill="#DC2626" d="M30 2 L33 12 L44 8 L38 18 L50 20 L40 26 L48 36 L35 32 L33 50 L30 68 L27 50 L25 32 L12 36 L20 26 L10 20 L22 18 L16 8 L27 12 Z"/>
      <line x1="30" y1="12" x2="30" y2="60" stroke="#991B1B" stroke-width="1.2"/>
    </svg>`,
    // 2. Oak Leaf (Warm Orange)
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 65" width="26" height="34" style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.15));">
      <path fill="#EA580C" d="M25 5 C25 5 32 12 36 10 C40 8 38 16 42 18 C46 20 42 26 44 30 C46 34 40 36 38 40 C36 44 30 42 28 48 L25 62 L22 48 C20 42 14 44 12 40 C10 36 4 34 6 30 C8 26 4 20 8 18 C12 16 10 8 14 10 C18 12 25 5 25 5Z"/>
      <line x1="25" y1="10" x2="25" y2="58" stroke="#9A3412" stroke-width="1.2"/>
    </svg>`,
    // 3. Aspen Gold Leaf (Golden Yellow)
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 60" width="22" height="30" style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.15));">
      <path fill="#F59E0B" d="M22 4 C32 12 42 26 38 42 C34 54 26 56 22 58 C18 56 10 54 6 42 C2 26 12 12 22 4 Z"/>
      <line x1="22" y1="8" x2="22" y2="54" stroke="#B45309" stroke-width="1.2"/>
    </svg>`,
    // 4. Elm Leaf (Russet Brown)
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 55" width="20" height="28" style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.15));">
      <path fill="#92400E" d="M20 2 C20 2 38 20 38 36 C38 46 30 54 20 54 C10 54 2 46 2 36 C2 20 20 2 20 2Z"/>
      <line x1="20" y1="8" x2="20" y2="50" stroke="#78350F" stroke-width="1.2"/>
    </svg>`,
    // 5. Broad Maple (Harvest Amber)
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 70 65" width="34" height="32" style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.15));">
      <path fill="#D97706" d="M35 3 L39 14 L52 9 L44 22 L60 22 L48 30 L58 42 L42 36 L40 55 L35 65 L30 55 L28 36 L12 42 L22 30 L10 22 L26 22 L18 9 L31 14 Z"/>
      <line x1="35" y1="12" x2="35" y2="58" stroke="#78350F" stroke-width="1.2"/>
    </svg>`,
  ];

  /* ── Detailed Turkey SVG Mascot ────────────────────────── */
  const TURKEY_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 86 96" width="68" height="76">
    <!-- Fan of Tail Feathers -->
    <ellipse cx="18" cy="40" rx="9" ry="24" fill="#DC2626" transform="rotate(-40,18,40)"/>
    <ellipse cx="28" cy="27" rx="9" ry="24" fill="#EA580C" transform="rotate(-20,28,27)"/>
    <ellipse cx="43" cy="22" rx="9" ry="24" fill="#F59E0B" transform="rotate(0,43,22)"/>
    <ellipse cx="58" cy="27" rx="9" ry="24" fill="#D97706" transform="rotate(20,58,27)"/>
    <ellipse cx="68" cy="40" rx="9" ry="24" fill="#92400E" transform="rotate(40,68,40)"/>
    
    <!-- Inner Feathers Highlights -->
    <ellipse cx="43" cy="24" rx="4" ry="16" fill="#FDE68A" opacity="0.6"/>
    <ellipse cx="30" cy="28" rx="4" ry="16" fill="#FDE68A" transform="rotate(-20,30,28)" opacity="0.6"/>
    <ellipse cx="56" cy="28" rx="4" ry="16" fill="#FDE68A" transform="rotate(20,56,28)" opacity="0.6"/>

    <!-- Plump Body -->
    <ellipse cx="43" cy="65" rx="24" ry="21" fill="#78350F"/>
    <!-- Wing -->
    <ellipse cx="38" cy="66" rx="14" ry="12" fill="#582407" transform="rotate(-15,38,66)"/>

    <!-- Turkey Neck & Head -->
    <path d="M 43 56 Q 48 42 52 38 Q 56 34 52 28 Q 46 26 44 32 Q 40 40 43 56 Z" fill="#92400E"/>
    <circle cx="50" cy="30" r="10" fill="#92400E"/>

    <!-- Eye -->
    <circle cx="53" cy="28" r="3" fill="#FFFFFF"/>
    <circle cx="54.5" cy="28" r="1.6" fill="#0F172A"/>
    <circle cx="55.2" cy="27.2" r="0.6" fill="#FFFFFF"/>

    <!-- Beak -->
    <polygon points="59,29 69,33 59,37" fill="#F59E0B"/>

    <!-- Snood & Wattle -->
    <path d="M 59 31 C 63 32 64 38 60 41 C 57 43 57 37 59 31 Z" fill="#DC2626"/>
    <ellipse cx="56" cy="39" rx="3.5" ry="7" fill="#EF4444"/>

    <!-- Legs & Feet -->
    <line x1="36" y1="84" x2="34" y2="94" stroke="#B45309" stroke-width="3.5" stroke-linecap="round"/>
    <line x1="34" y1="94" x2="25" y2="94" stroke="#B45309" stroke-width="2.8" stroke-linecap="round"/>
    <line x1="34" y1="94" x2="38" y2="95" stroke="#B45309" stroke-width="2.8" stroke-linecap="round"/>

    <line x1="50" y1="84" x2="52" y2="94" stroke="#B45309" stroke-width="3.5" stroke-linecap="round"/>
    <line x1="52" y1="94" x2="60" y2="94" stroke="#B45309" stroke-width="2.8" stroke-linecap="round"/>
    <line x1="52" y1="94" x2="46" y2="95" stroke="#B45309" stroke-width="2.8" stroke-linecap="round"/>
  </svg>`;

  /* ── Golden Wheat Sheaf SVG ────────────────────────────── */
  const WHEAT_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 160" width="90" height="140">
    <line x1="50" y1="160" x2="28" y2="40" stroke="#CA8A04" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="50" y1="160" x2="42" y2="34" stroke="#CA8A04" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="50" y1="160" x2="52" y2="32" stroke="#CA8A04" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="50" y1="160" x2="62" y2="36" stroke="#CA8A04" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="50" y1="160" x2="74" y2="44" stroke="#CA8A04" stroke-width="2.5" stroke-linecap="round"/>

    <ellipse cx="28" cy="32" rx="5.5" ry="11" fill="#D97706"/>
    <ellipse cx="42" cy="26" rx="5.5" ry="11" fill="#FBBF24"/>
    <ellipse cx="52" cy="25" rx="5.5" ry="11" fill="#D97706"/>
    <ellipse cx="62" cy="28" rx="5.5" ry="11" fill="#FBBF24"/>
    <ellipse cx="74" cy="35" rx="5" ry="10" fill="#D97706"/>

    <path d="M 36 108 Q 50 102 64 108 Q 58 116 50 116 Q 42 116 36 108Z" fill="#92400E"/>
  </svg>`;

  function rand(min, max) {
    return Math.random() * (max - min) + min;
  }

  /* ── Falling Leaf Generator ─────────────────────────────── */
  let leafTimer = null;

  function spawnLeaf() {
    if (!document.body.classList.contains('thanksgiving-active')) return;
    const leaf = document.createElement('div');
    leaf.className = 'tg-leaf';
    const svg = LEAF_SVGS[Math.floor(Math.random() * LEAF_SVGS.length)];
    leaf.innerHTML = svg;

    const left = rand(2, 96);
    const duration = rand(7, 14);
    const delay = rand(0, 3);
    const scale = rand(0.75, 1.15);

    leaf.style.left = left + 'vw';
    leaf.style.animationDuration = duration + 's';
    leaf.style.animationDelay = delay + 's';
    leaf.style.transform = `scale(${scale})`;

    document.body.appendChild(leaf);

    setTimeout(() => {
      if (leaf.parentNode) {
        leaf.parentNode.removeChild(leaf);
      }
    }, (duration + delay + 1) * 1000);
  }

  /* ── Injections ─────────────────────────────────────────── */
  function injectTurkey() {
    if (document.getElementById('tg-turkey-mascot')) return;
    const div = document.createElement('div');
    div.id = 'tg-turkey-mascot';
    div.innerHTML = TURKEY_SVG;
    div.setAttribute('aria-label', 'Thanksgiving Turkey');
    div.addEventListener('click', () => {
      div.style.transform = 'scale(1.3) rotate(20deg)';
      setTimeout(() => {
        div.style.transform = '';
      }, 300);
      for (let i = 0; i < 4; i++) {
        setTimeout(spawnLeaf, i * 200);
      }
    });
    document.body.appendChild(div);
  }

  function injectWheat() {
    ['top-left', 'bot-right'].forEach(pos => {
      if (document.querySelector('.tg-wheat-corner.' + pos)) return;
      const el = document.createElement('div');
      el.className = 'tg-wheat-corner ' + pos;
      el.innerHTML = WHEAT_SVG;
      document.body.appendChild(el);
    });
  }

  function injectToggleButton() {
    if (document.getElementById('tg-toggle-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'tg-toggle-btn';
    btn.setAttribute('title', 'Toggle Thanksgiving Festival Theme');
    btn.innerHTML = '🦃';
    btn.addEventListener('click', () => {
      const isNowActive = document.body.classList.toggle('thanksgiving-active');
      localStorage.setItem(STORAGE_KEY, isNowActive ? '1' : '0');
      if (isNowActive) {
        startEffects();
      } else {
        stopEffects();
      }
    });
    document.body.appendChild(btn);
  }

  function startEffects() {
    injectTurkey();
    injectWheat();
    if (!leafTimer) {
      for (let i = 0; i < 6; i++) {
        setTimeout(spawnLeaf, i * 500);
      }
      leafTimer = setInterval(spawnLeaf, 2200);
    }
  }

  function stopEffects() {
    if (leafTimer) {
      clearInterval(leafTimer);
      leafTimer = null;
    }
    document.querySelectorAll('.tg-leaf').forEach(el => el.remove());
    const mascot = document.getElementById('tg-turkey-mascot');
    if (mascot) mascot.remove();
    document.querySelectorAll('.tg-wheat-corner').forEach(el => el.remove());
  }

  function init() {
    injectToggleButton();
    const stored = localStorage.getItem(STORAGE_KEY);
    const shouldActivate = stored === null ? true : stored === '1';
    if (shouldActivate) {
      document.body.classList.add('thanksgiving-active');
      startEffects();
    }
  }


  /* ── Bulletproof "Got it" & SweetAlert Modal Closer ─────── */
  document.addEventListener('click', function (e) {
    var target = e.target;
    if (!target) return;

    // SweetAlert2 confirm button ("Got it")
    var isSwalConfirm = target.matches('.swal2-confirm, .portal-swal-confirm') ||
      target.closest('.swal2-confirm, .portal-swal-confirm') ||
      (target.textContent && target.textContent.trim() === 'Got it' && target.closest('.swal2-popup, .swal2-container'));

    if (isSwalConfirm) {
      if (window.Swal && typeof window.Swal.close === 'function') {
        window.Swal.close();
      }
      var swalContainer = document.querySelector('.swal2-container');
      if (swalContainer) {
        swalContainer.style.setProperty('display', 'none', 'important');
        if (swalContainer.parentNode) {
          setTimeout(function() {
            if (swalContainer.parentNode) swalContainer.parentNode.removeChild(swalContainer);
          }, 150);
        }
      }
    }

    // Site news alert modal ("Got it" or dismiss)
    var isNewsGotIt = target.matches('[data-site-news-got-it], .site-news-alert-btn') ||
      target.closest('[data-site-news-got-it], .site-news-alert-btn');

    if (isNewsGotIt) {
      var newsModal = document.getElementById('siteNewsAlertModal');
      if (newsModal) {
        newsModal.classList.remove('is-open');
        newsModal.style.setProperty('display', 'none', 'important');
        document.body.classList.remove('portal-modal-open');
      }
    }
  }, true);

    if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
