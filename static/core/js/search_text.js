(function () {
  function collapse(value) {
    return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function compact(value) {
    return collapse(value).replace(/[\s\-]+/g, "");
  }

  function editDistance(a, b) {
    var prev = [];
    var next = [];
    var i;
    var j;
    for (j = 0; j <= b.length; j += 1) prev[j] = j;
    for (i = 1; i <= a.length; i += 1) {
      next[0] = i;
      for (j = 1; j <= b.length; j += 1) {
        var cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
        next[j] = Math.min(next[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
      }
      var swap = prev;
      prev = next;
      next = swap;
    }
    return prev[b.length];
  }

  function ratio(a, b) {
    if (!a || !b) return 0;
    if (a === b) return 1;
    if (Math.abs(a.length - b.length) > 8) return 0;
    if (a.length > 40 || b.length > 40) return 0;
    return 1 - editDistance(a, b) / Math.max(a.length, b.length);
  }

  window.regiSearchMatch = function (haystack, query) {
    var raw = collapse(query);
    if (!raw) return true;
    var hay = collapse(haystack);
    if (hay.indexOf(raw) !== -1) return true;
    var compactQuery = compact(raw);
    var compactHay = compact(hay);
    return compactQuery.length >= 2 && compactHay.indexOf(compactQuery) !== -1;
  };

  window.regiSearchNear = function (haystack, query) {
    var needle = compact(query);
    if (needle.length < 4) return false;
    var hay = compact(haystack);
    if (ratio(needle, hay) >= 0.84) return true;
    var parts = collapse(haystack).split(/[^a-z0-9]+/);
    for (var i = 0; i < parts.length; i += 1) {
      if (parts[i].length >= 4 && ratio(needle, parts[i]) >= 0.84) return true;
    }
    return false;
  };
})();
