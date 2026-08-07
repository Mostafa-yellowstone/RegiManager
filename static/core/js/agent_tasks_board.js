(function () {
  var root = document.querySelector(".atb");
  if (!root) return;

  var NOTE_STATUSES = { in_progress: true, waiting: true, done: true };
  var STATUS_LABELS = {
    todo: "To do",
    in_progress: "In progress",
    waiting: "Waiting",
    done: "Done",
  };

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function toggleUrl(taskId) {
    var template = root.getAttribute("data-toggle-url-template") || "";
    return template.replace(/0\/?$/, taskId + "/").replace("/0/", "/" + taskId + "/");
  }

  function updateCounts(data) {
    ["todo", "in_progress", "waiting", "done"].forEach(function (key) {
      var el = document.querySelector("[data-count-" + key + "]");
      if (el && typeof data[key] !== "undefined") el.textContent = data[key];
    });
    var counts = document.getElementById("atbProgressCounts");
    if (counts && typeof data.done !== "undefined") {
      counts.textContent = data.done + "/" + data.total + " done";
    }
    var openMeta = document.getElementById("atbProgressOpen");
    if (openMeta) {
      openMeta.textContent =
        (data.open || 0) + " open · " + (data.in_progress || 0) + " in progress";
    }
    var pct = document.getElementById("taskProgressPct");
    if (pct && typeof data.percent !== "undefined") pct.textContent = data.percent + "%";
    var ring = document.getElementById("atbProgressFg");
    if (ring && typeof data.percent !== "undefined") {
      ring.setAttribute("stroke-dasharray", data.percent + ", 100");
    }
  }

  function postStatus(taskId, status, note) {
    var body = new FormData();
    body.append("csrfmiddlewaretoken", getCookie("csrftoken"));
    body.append("status", status);
    if (typeof note === "string") body.append("completion_note", note);

    return fetch(toggleUrl(taskId), {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body: body,
      credentials: "same-origin",
    }).then(function (r) {
      return r.json().then(function (data) {
        return { ok: r.ok && data && data.ok, status: r.status, data: data || {} };
      });
    });
  }

  var modal = document.getElementById("atbCompleteModal");
  var noteInput = document.getElementById("atbCompleteNote");
  var titleEl = document.getElementById("atbCompleteTaskTitle");
  var headingEl = document.getElementById("atbCompleteHeading");
  var leadEl = document.getElementById("atbCompleteLead");
  var labelEl = document.getElementById("atbCompleteLabel");
  var submitBtn = document.getElementById("atbCompleteSubmit");
  var errorEl = document.getElementById("atbCompleteError");
  var cancelBtn = document.getElementById("atbCompleteCancel");
  var completeForm = document.getElementById("atbCompleteForm");
  var pendingTaskId = null;
  var pendingStatus = "done";

  function openStageNoteModal(taskId, title, status) {
    pendingTaskId = taskId;
    pendingStatus = status || "done";
    var label = STATUS_LABELS[pendingStatus] || "Update";
    if (headingEl) headingEl.textContent = label + " task";
    if (leadEl) {
      leadEl.textContent =
        pendingStatus === "done"
          ? "Leave a short note about what you finished."
          : "Add a progress note for this stage.";
    }
    if (labelEl) labelEl.textContent = label + " note";
    if (submitBtn) {
      submitBtn.textContent =
        pendingStatus === "done" ? "Mark done" : "Save & move to " + label.toLowerCase();
    }
    if (titleEl) titleEl.textContent = title || "Task #" + taskId;
    if (noteInput) {
      noteInput.value = "";
      noteInput.placeholder =
        pendingStatus === "done"
          ? "What did you do? Any follow-up?"
          : "What is happening at this stage?";
      noteInput.required = true;
    }
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = "";
    }
    if (modal && typeof modal.showModal === "function") modal.showModal();
    if (noteInput) noteInput.focus();
  }

  function closeStageNoteModal() {
    pendingTaskId = null;
    pendingStatus = "done";
    if (modal && typeof modal.close === "function") modal.close();
  }

  if (cancelBtn) cancelBtn.addEventListener("click", closeStageNoteModal);
  if (completeForm) {
    completeForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!pendingTaskId || !pendingStatus) return;
      var note = noteInput ? noteInput.value.trim() : "";
      if (!note) {
        if (errorEl) {
          errorEl.hidden = false;
          errorEl.textContent = "Please leave a progress note.";
        }
        return;
      }
      postStatus(pendingTaskId, pendingStatus, note).then(function (result) {
        if (!result.ok) {
          if (errorEl) {
            errorEl.hidden = false;
            errorEl.textContent =
              (result.data && result.data.error) || "Could not update task.";
          }
          return;
        }
        closeStageNoteModal();
        window.location.reload();
      });
    });
  }

  root.addEventListener("click", function (event) {
    var completeBtn = event.target.closest("[data-complete-task]");
    if (completeBtn) {
      event.preventDefault();
      openStageNoteModal(
        completeBtn.getAttribute("data-task-id"),
        completeBtn.getAttribute("data-task-title"),
        "done"
      );
      return;
    }
    var stageBtn = event.target.closest("[data-set-status]");
    if (!stageBtn) return;
    event.preventDefault();
    var taskId = stageBtn.getAttribute("data-task-id");
    var status = stageBtn.getAttribute("data-set-status");
    var title =
      stageBtn.getAttribute("data-task-title") ||
      (stageBtn.closest("[data-task-id]") &&
        stageBtn.closest("[data-task-id]").querySelector(".atb-card__title, .atb-list-row__main strong") &&
        stageBtn.closest("[data-task-id]").querySelector(".atb-card__title, .atb-list-row__main strong")
          .textContent) ||
      "";
    if (!taskId || !status) return;
    if (NOTE_STATUSES[status]) {
      openStageNoteModal(taskId, title.trim(), status);
      return;
    }
    stageBtn.disabled = true;
    postStatus(taskId, status).then(function (result) {
      stageBtn.disabled = false;
      if (!result.ok) {
        window.alert((result.data && result.data.error) || "Could not update task.");
        return;
      }
      updateCounts(result.data);
      window.location.reload();
    });
  });
})();
