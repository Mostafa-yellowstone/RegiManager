(function () {
  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  var photoInput = document.getElementById("agent-photo-input");
  var photoForm = document.getElementById("agentPhotoForm");
  if (photoInput && photoForm) {
    photoInput.addEventListener("change", function () {
      if (photoInput.files && photoInput.files.length) {
        photoForm.submit();
      }
    });
  }

  var spacesBtn = document.getElementById("spacesPickerBtn");
  var spacesModal = document.getElementById("spacesPickerModal");
  var spacesClose = document.getElementById("spacesPickerClose");
  var spacesDismiss = document.getElementById("spacesPickerDismiss");

  function openSpacesModal() {
    if (!spacesModal || typeof spacesModal.showModal !== "function") return;
    spacesModal.showModal();
    var first = spacesModal.querySelector(".agent-space-tile, .agent-spaces-close");
    if (first) first.focus();
  }

  function closeSpacesModal() {
    if (!spacesModal || typeof spacesModal.close !== "function") return;
    spacesModal.close();
    if (spacesBtn) spacesBtn.focus();
  }

  if (spacesBtn && spacesModal) {
    spacesBtn.addEventListener("click", openSpacesModal);
    if (spacesClose) spacesClose.addEventListener("click", closeSpacesModal);
    if (spacesDismiss) spacesDismiss.addEventListener("click", closeSpacesModal);
    spacesModal.addEventListener("click", function (event) {
      if (event.target === spacesModal) closeSpacesModal();
    });
    spacesModal.addEventListener("cancel", function (event) {
      event.preventDefault();
      closeSpacesModal();
    });
  }

  document.querySelectorAll(".agent-task-form").forEach(function (form) {
    var checkbox = form.querySelector(".agent-check__input");
    if (!checkbox) return;
    checkbox.addEventListener("change", function () {
      var item = form.closest(".agent-task");
      var csrf = form.querySelector("[name=csrfmiddlewaretoken]");
      var body = new FormData();
      body.append("csrfmiddlewaretoken", csrf ? csrf.value : getCookie("csrftoken"));
      body.append("toggle", "1");

      fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: body,
        credentials: "same-origin",
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.ok) return;
          if (item) item.classList.toggle("is-done", !!data.is_done);
          checkbox.checked = !!data.is_done;
          var pct = document.getElementById("taskProgressPct");
          if (pct) pct.textContent = (data.percent || 0) + "%";
          var ring = document.querySelector(".agent-progress__fg");
          if (ring) ring.setAttribute("stroke-dasharray", (data.percent || 0) + ", 100");
          var pill = document.querySelector(".agent-card--tasks .agent-pill");
          if (pill && typeof data.done !== "undefined") {
            pill.textContent = data.done + "/" + data.total;
          }
        })
        .catch(function () {
          form.submit();
        });
    });
  });
})();
