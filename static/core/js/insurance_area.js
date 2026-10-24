(function () {
  var root = document.querySelector('.ina');
  if (!root) return;

  function setOpen(open) {
    root.classList.toggle('is-menu-open', open);
    document.body.style.overflow = open ? 'hidden' : '';
  }

  document.querySelectorAll('[data-ina-open]').forEach(function (btn) {
    btn.addEventListener('click', function () { setOpen(true); });
  });
  document.querySelectorAll('[data-ina-close]').forEach(function (btn) {
    btn.addEventListener('click', function () { setOpen(false); });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && root.classList.contains('is-menu-open')) setOpen(false);
  });

  var search = document.getElementById('inaSearch');
  if (!search) return;
  var input = document.getElementById('inaSearchInput');
  var results = document.getElementById('inaSearchResults');
  var hint = results.innerHTML;
  var timer = null;
  var controller = null;
  var activeIndex = -1;

  function items() {
    return Array.prototype.slice.call(results.querySelectorAll('.ina-search__item'));
  }

  function setActive(index) {
    var list = items();
    if (!list.length) { activeIndex = -1; return; }
    activeIndex = (index + list.length) % list.length;
    list.forEach(function (el, i) {
      el.classList.toggle('is-active', i === activeIndex);
      el.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
    });
    list[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  function message(text) {
    results.innerHTML = '';
    var p = document.createElement('p');
    p.className = 'ina-search__hint';
    p.textContent = text;
    results.appendChild(p);
    activeIndex = -1;
  }

  function render(data) {
    results.innerHTML = '';
    if (!data.groups.length) { message('No matches for "' + data.q + '".'); return; }
    data.groups.forEach(function (group) {
      var title = document.createElement('div');
      title.className = 'ina-search__group';
      title.textContent = group.title;
      results.appendChild(title);
      group.items.forEach(function (item) {
        var a = document.createElement('a');
        a.className = 'ina-search__item';
        a.href = item.url;
        a.setAttribute('role', 'option');
        var label = document.createElement('span');
        label.className = 'ina-search__label';
        label.textContent = item.label;
        var meta = document.createElement('span');
        meta.className = 'ina-search__meta';
        meta.textContent = item.meta || '';
        a.appendChild(label);
        a.appendChild(meta);
        results.appendChild(a);
      });
    });
    setActive(0);
  }

  function run() {
    var q = input.value.trim();
    if (q.length < 2) { results.innerHTML = hint; activeIndex = -1; return; }
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(search.dataset.url + '?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      signal: controller.signal,
      credentials: 'same-origin'
    })
      .then(function (r) { if (!r.ok) throw new Error('search failed'); return r.json(); })
      .then(render)
      .catch(function (err) { if (err.name !== 'AbortError') message('Search is unavailable right now.'); });
  }

  function openSearch() {
    search.hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(function () { input.focus(); input.select(); }, 10);
  }

  function closeSearch() {
    search.hidden = true;
    document.body.style.overflow = '';
  }

  document.querySelectorAll('[data-ina-search-open]').forEach(function (btn) {
    btn.addEventListener('click', openSearch);
  });
  search.querySelectorAll('[data-ina-search-close]').forEach(function (el) {
    el.addEventListener('click', closeSearch);
  });

  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(run, 180);
  });

  input.addEventListener('keydown', function (event) {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(activeIndex + 1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(activeIndex - 1); }
    else if (event.key === 'Enter') {
      var list = items();
      if (activeIndex >= 0 && list[activeIndex]) { event.preventDefault(); window.location.href = list[activeIndex].href; }
    }
  });

  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && (event.key === 'k' || event.key === 'K')) {
      event.preventDefault();
      if (search.hidden) openSearch(); else closeSearch();
    } else if (event.key === 'Escape' && !search.hidden) {
      closeSearch();
    }
  });
})();
