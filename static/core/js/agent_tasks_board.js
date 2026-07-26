(function () {
  var root = document.querySelector(".atb");
  if (!root) return;

  function updateBoardCounts(data) {
    var openEl = document.querySelector("[data-count-open]");
    var doneEl = document.querySelector("[data-count-done]");
    var counts = document.getElementById("atbProgressCounts");
    var openCount =
      typeof data.open !== "undefined"
        ? data.open
        : Math.max((data.total || 0) - (data.done || 0), 0);
    if (openEl) openEl.textContent = openCount;
    if (doneEl && typeof data.done !== "undefined") doneEl.textContent = data.done;
    if (counts && typeof data.done !== "undefined") {
      counts.textContent = data.done + "/" + data.total + " done";
    }
    var metaSmall = document.querySelector(".atb-progress__meta small");
    if (metaSmall) metaSmall.textContent = openCount + " open";
  }

  function moveCard(item, isDone) {
    if (!item || !item.classList.contains("atb-card")) return;
    var openList = document.getElementById("atbOpenCards");
    var doneList = document.getElementById("atbDoneCards");
    if (!openList || !doneList) return;

    item.classList.add("is-flying");
    window.setTimeout(function () {
      item.classList.remove("is-flying");
      item.classList.toggle("is-done", !!isDone);
      var checkbox = item.querySelector(".agent-check__input");
      if (checkbox) checkbox.checked = !!isDone;

      var emptyOpen = openList.querySelector(".atb-empty");
      var emptyDone = doneList.querySelector(".atb-empty");
      if (isDone) {
        if (emptyDone) emptyDone.remove();
        doneList.prepend(item);
        if (!openList.querySelector(".atb-card")) {
          openList.innerHTML = '<li class="atb-empty">All clear — no open tasks.</li>';
        }
      } else {
        if (emptyOpen) emptyOpen.remove();
        openList.prepend(item);
        if (!doneList.querySelector(".atb-card")) {
          doneList.innerHTML = '<li class="atb-empty">Nothing completed yet.</li>';
        }
      }
    }, 280);
  }

  document.querySelectorAll(".atb .agent-task-form").forEach(function (form) {
    form.addEventListener("atb:toggled", function (event) {
      var data = event.detail || {};
      var item = form.closest(".agent-task");
      updateBoardCounts(data);
      if (item && item.classList.contains("atb-card")) {
        moveCard(item, !!data.is_done);
      } else if (item && item.classList.contains("atb-list-row")) {
        item.classList.toggle("is-done", !!data.is_done);
        var chip = item.querySelector(".atb-status-chip");
        if (chip) {
          chip.classList.toggle("is-done", !!data.is_done);
          chip.classList.toggle("is-open", !data.is_done);
          chip.textContent = data.is_done ? "Done" : "Open";
        }
      }
    });
  });
})();
