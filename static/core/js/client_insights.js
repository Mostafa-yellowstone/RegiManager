(function () {
    "use strict";

    function initTimeline(root) {
        var items = Array.prototype.slice.call(root.querySelectorAll("[data-ci-kind]"));
        var moreBtn = root.querySelector("[data-ci-more-btn]");
        var expanded = false;
        var filter = "";

        function render() {
            var shown = 0;
            items.forEach(function (li) {
                var match = !filter || li.getAttribute("data-ci-kind") === filter;
                var visible = match && (expanded || filter || shown < 12);
                li.hidden = !visible;
                if (match) shown += 1;
            });
            if (moreBtn) moreBtn.hidden = expanded || !!filter;
        }

        root.querySelectorAll("[data-ci-filter]").forEach(function (chip) {
            chip.addEventListener("click", function () {
                filter = chip.getAttribute("data-ci-filter");
                root.querySelectorAll("[data-ci-filter]").forEach(function (c) {
                    c.classList.toggle("is-active", c === chip);
                });
                render();
            });
        });
        if (moreBtn) {
            moreBtn.addEventListener("click", function () {
                expanded = true;
                render();
            });
        }
    }

    function initSearch(form) {
        var url = form.getAttribute("data-ci-search");
        var input = form.querySelector("[data-ci-search-input]");
        var list = form.querySelector("[data-ci-search-results]");
        var hidden = form.querySelector("input[name=other_id]");
        var submit = form.querySelector("[data-ci-search-submit]");
        var timer = null;
        var seq = 0;

        function pick(btn, id, name) {
            hidden.value = id;
            input.value = name;
            submit.disabled = false;
            list.querySelectorAll("button").forEach(function (b) {
                b.classList.toggle("is-picked", b === btn);
            });
            list.hidden = true;
        }

        function show(results) {
            list.innerHTML = "";
            results.forEach(function (r) {
                var li = document.createElement("li");
                var btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = r.name;
                if (r.detail) {
                    var small = document.createElement("small");
                    small.textContent = r.detail;
                    btn.appendChild(small);
                }
                btn.addEventListener("click", function () { pick(btn, r.id, r.name); });
                li.appendChild(btn);
                list.appendChild(li);
            });
            list.hidden = results.length === 0;
        }

        input.addEventListener("input", function () {
            hidden.value = "";
            submit.disabled = true;
            clearTimeout(timer);
            var q = input.value.trim();
            if (q.length < 2) {
                show([]);
                return;
            }
            timer = setTimeout(function () {
                var mine = ++seq;
                fetch(url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
                    .then(function (r) { return r.ok ? r.json() : { results: [] }; })
                    .then(function (data) { if (mine === seq) show(data.results || []); })
                    .catch(function () { show([]); });
            }, 220);
        });
    }

    function init() {
        document.querySelectorAll("[data-ci-timeline]").forEach(initTimeline);
        document.querySelectorAll("[data-ci-search]").forEach(initSearch);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
