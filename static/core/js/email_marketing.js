(function () {
    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }
    function qsa(sel, root) {
        return Array.from((root || document).querySelectorAll(sel));
    }

    function openModal(id) {
        var modal = document.getElementById(id);
        if (!modal) return;
        modal.hidden = false;
        document.body.classList.add("em-modal-open");
        var firstInput = modal.querySelector("input:not([type='hidden']), textarea, select");
        if (firstInput) {
            window.setTimeout(function () { firstInput.focus(); }, 80);
        }
    }
    function closeModals() {
        qsa(".em-modal").forEach(function (m) { m.hidden = true; });
        document.body.classList.remove("em-modal-open");
    }

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeModals();
    });

    document.addEventListener("click", function (e) {
        if (e.target.matches("[data-close-modal]") || e.target.classList.contains("em-modal-backdrop")) {
            closeModals();
        }
        var openCreate = e.target.closest("#em-open-create-list, #em-open-create-list-empty");
        if (openCreate) {
            e.preventDefault();
            openModal("em-create-list-modal");
        }
    });

    var createListForm = document.getElementById("em-create-list-form");
    if (createListForm) {
        createListForm.addEventListener("submit", function () {
            var btn = document.getElementById("em-create-list-submit");
            if (!btn || btn.disabled) return;
            btn.disabled = true;
            btn.textContent = "Creating…";
        });
    }

    var importFile = document.getElementById("em-import-file");
    var importFileName = document.getElementById("em-import-file-name");
    var importForm = document.getElementById("em-import-form");
    if (importFile && importFileName) {
        importFile.addEventListener("change", function () {
            var file = importFile.files && importFile.files[0];
            if (file) {
                importFileName.textContent = file.name;
                importFileName.hidden = false;
            } else {
                importFileName.textContent = "";
                importFileName.hidden = true;
            }
        });
    }
    if (importForm) {
        importForm.addEventListener("submit", function () {
            var btn = document.getElementById("em-import-submit");
            if (!btn || btn.disabled) return;
            btn.disabled = true;
            btn.textContent = "Importing…";
        });
    }

    var addBtn = document.getElementById("em-add-contact-btn");
    if (addBtn) {
        addBtn.addEventListener("click", function () {
            var form = document.getElementById("em-contact-form");
            if (form) form.reset();
            var cid = document.getElementById("contact_id");
            if (cid) cid.value = "";
            document.getElementById("em-contact-modal-title").textContent = "Add contact";
            openModal("em-contact-modal");
        });
    }

    qsa(".em-edit-contact").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var d = btn.dataset;
            document.getElementById("contact_id").value = d.id || "";
            document.getElementById("contact_name").value = d.name || "";
            document.getElementById("contact_address_line1").value = d.address_line1 || "";
            document.getElementById("contact_address_line2").value = d.address_line2 || "";
            document.getElementById("contact_address_line3").value = d.address_line3 || "";
            document.getElementById("contact_city").value = d.city || "";
            document.getElementById("contact_state").value = d.state || "";
            document.getElementById("contact_zip_code").value = d.zip_code || "";
            document.getElementById("contact_phone").value = d.phone || "";
            document.getElementById("contact_email").value = d.email || "";
            document.getElementById("contact_website").value = d.website || "";
            document.getElementById("contact_notes").value = d.notes || "";
            document.getElementById("em-contact-modal-title").textContent = "Edit contact";
            openModal("em-contact-modal");
        });
    });

    function resetAssignTaskModal() {
        var form = document.getElementById("em-assign-task-form");
        if (!form) return;
        form.reset();
        var cid = document.getElementById("assign_contact_id");
        var cids = document.getElementById("assign_contact_ids");
        var clabel = document.getElementById("assign_contact_label");
        var ctx = document.getElementById("em-assign-context");
        if (cid) cid.value = "";
        if (cids) cids.value = "";
        if (clabel) clabel.value = "";
        if (ctx) {
            ctx.textContent = "";
            ctx.hidden = true;
        }
        var titleEl = document.getElementById("em-assign-task-modal-title");
        if (titleEl) titleEl.textContent = "Assign task";
        var submitBtn = document.getElementById("em-assign-task-submit");
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Assign to agent";
        }
    }

    function selectedContactChecks() {
        return qsa(".em-contact-check:checked");
    }

    function syncBulkSelection() {
        var checks = selectedContactChecks();
        var count = checks.length;
        var bar = document.getElementById("em-bulk-bar");
        var bulkBtn = document.getElementById("em-bulk-assign-btn");
        var countEl = document.getElementById("em-bulk-count");
        var label = document.getElementById("em-bulk-bar-label");
        if (countEl) countEl.textContent = String(count);
        if (label) label.textContent = count === 1 ? "1 selected" : count + " selected";
        if (bar) bar.hidden = count === 0;
        if (bulkBtn) bulkBtn.hidden = count === 0;
        var all = document.getElementById("em-select-all");
        var pageChecks = qsa(".em-contact-check");
        if (all && pageChecks.length) {
            all.checked = pageChecks.every(function (c) { return c.checked; });
            all.indeterminate = !all.checked && pageChecks.some(function (c) { return c.checked; });
        }
    }

    function openAssignTaskModal(fromContactBtn, bulkIds, bulkNames) {
        resetAssignTaskModal();
        var titleInput = document.getElementById("assign_task_title");
        var noteInput = document.getElementById("assign_task_note");
        var cid = document.getElementById("assign_contact_id");
        var cids = document.getElementById("assign_contact_ids");
        var clabel = document.getElementById("assign_contact_label");
        var ctx = document.getElementById("em-assign-context");
        var modalTitle = document.getElementById("em-assign-task-modal-title");

        if (bulkIds && bulkIds.length > 1) {
            if (cids) cids.value = bulkIds.join(",");
            if (cid) cid.value = "";
            if (clabel) clabel.value = bulkIds.length + " CRM contacts";
            if (titleInput) titleInput.value = "Follow up · " + bulkIds.length + " CRM leads";
            if (noteInput) {
                noteInput.value = "Please work these CRM leads from Email Marketing.\n" +
                    (bulkNames || []).slice(0, 12).map(function (n) { return "• " + n; }).join("\n") +
                    (bulkNames && bulkNames.length > 12 ? "\n• …and " + (bulkNames.length - 12) + " more" : "");
            }
            if (ctx) {
                ctx.textContent = "Bulk assign: " + bulkIds.length + " selected contacts on this page.";
                ctx.hidden = false;
            }
            if (modalTitle) modalTitle.textContent = "Bulk assign · " + bulkIds.length + " contacts";
        } else if (fromContactBtn) {
            var d = fromContactBtn.dataset;
            var name = d.name || "Contact";
            if (cid) cid.value = d.id || "";
            if (cids) cids.value = d.id || "";
            if (clabel) clabel.value = name;
            if (titleInput) titleInput.value = "Follow up: " + name;
            var noteParts = [];
            if (d.email) noteParts.push("Email: " + d.email);
            if (d.phone) noteParts.push("Phone: " + d.phone);
            if (d.city || d.state) {
                noteParts.push("Location: " + [d.city, d.state].filter(Boolean).join(", "));
            }
            if (noteInput) {
                noteInput.value = noteParts.length
                    ? "Please take action on this CRM lead.\n" + noteParts.join("\n")
                    : "Please take action on this CRM lead.";
            }
            if (ctx) {
                ctx.textContent = "Linked contact: " + name;
                ctx.hidden = false;
            }
            if (modalTitle) modalTitle.textContent = "Assign · " + name;
        }
        openModal("em-assign-task-modal");
    }

    var assignBtn = document.getElementById("em-assign-task-btn");
    if (assignBtn) {
        assignBtn.addEventListener("click", function () {
            openAssignTaskModal(null);
        });
    }
    qsa(".em-assign-contact").forEach(function (btn) {
        btn.addEventListener("click", function () {
            openAssignTaskModal(btn);
        });
    });

    var selectAll = document.getElementById("em-select-all");
    if (selectAll) {
        selectAll.addEventListener("change", function () {
            qsa(".em-contact-check").forEach(function (c) {
                c.checked = selectAll.checked;
            });
            syncBulkSelection();
        });
    }
    qsa(".em-contact-check").forEach(function (c) {
        c.addEventListener("change", syncBulkSelection);
    });
    function openBulkAssign() {
        var checks = selectedContactChecks();
        if (!checks.length) return;
        openAssignTaskModal(
            null,
            checks.map(function (c) { return c.value; }),
            checks.map(function (c) { return c.dataset.name || ("#" + c.value); })
        );
    }
    var bulkOpen = document.getElementById("em-bulk-assign-open");
    var bulkBtn = document.getElementById("em-bulk-assign-btn");
    if (bulkOpen) bulkOpen.addEventListener("click", openBulkAssign);
    if (bulkBtn) bulkBtn.addEventListener("click", openBulkAssign);
    var bulkClear = document.getElementById("em-bulk-clear");
    if (bulkClear) {
        bulkClear.addEventListener("click", function () {
            qsa(".em-contact-check").forEach(function (c) { c.checked = false; });
            if (selectAll) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
            syncBulkSelection();
        });
    }
    syncBulkSelection();

    var assignForm = document.getElementById("em-assign-task-form");
    if (assignForm) {
        assignForm.addEventListener("submit", function () {
            var btn = document.getElementById("em-assign-task-submit");
            if (!btn || btn.disabled) return;
            btn.disabled = true;
            btn.textContent = "Assigning…";
        });
        var agentSelect = assignForm.querySelector('select[name="assigned_to"]');
        if (agentSelect) {
            agentSelect.classList.add("em-assign-select");
            agentSelect.required = true;
        }
    }

    qsa(".em-token").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var token = "{{" + btn.dataset.token + "}}";
            var ta = document.getElementById("html_content");
            if (!ta) return;
            var start = ta.selectionStart;
            var end = ta.selectionEnd;
            var val = ta.value;
            ta.value = val.slice(0, start) + token + val.slice(end);
            ta.focus();
            ta.selectionStart = ta.selectionEnd = start + token.length;
        });
    });

    function refreshPreview() {
        var cfg = window.EM_CONFIG;
        if (!cfg || !cfg.previewUrl) return;
        var html = document.getElementById("html_content");
        var css = document.getElementById("css_content");
        var contactSel = document.getElementById("em-preview-contact");
        var params = new URLSearchParams();
        if (html) params.set("html_content", html.value);
        if (css) params.set("css_content", css.value);
        if (contactSel && contactSel.value) params.set("contact_id", contactSel.value);
        fetch(cfg.previewUrl + "?" + params.toString(), { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var frame = document.getElementById("em-preview-frame");
                if (frame && data.html) frame.srcdoc = data.html;
            })
            .catch(function () {});
    }

    var refreshBtn = document.getElementById("em-refresh-preview");
    if (refreshBtn) refreshBtn.addEventListener("click", refreshPreview);

    var htmlTa = document.getElementById("html_content");
    var cssTa = document.getElementById("css_content");
    if (htmlTa) htmlTa.addEventListener("blur", refreshPreview);
    if (cssTa) cssTa.addEventListener("blur", refreshPreview);

    var uploadBtn = document.getElementById("em-upload-btn");
    if (uploadBtn) {
        uploadBtn.addEventListener("click", function () {
            var cfg = window.EM_CONFIG;
            var fileInput = document.getElementById("em-asset-file");
            if (!cfg || !fileInput || !fileInput.files.length) return;
            var fd = new FormData();
            fd.append("image", fileInput.files[0]);
            fd.append("csrfmiddlewaretoken", cfg.csrfToken);
            fetch(cfg.uploadUrl, { method: "POST", body: fd, credentials: "same-origin" })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.status !== "success") return;
                    var wrap = document.getElementById("em-assets");
                    if (!wrap) return;
                    var div = document.createElement("div");
                    div.className = "em-asset";
                    div.innerHTML = '<img src="' + data.url + '" alt="" data-url="' + data.url + '" title="Click to copy img tag"><div>' + (data.label || "image") + "</div>";
                    wrap.appendChild(div);
                    bindAssetClick(div.querySelector("img"));
                    fileInput.value = "";
                });
        });
    }

    function bindAssetClick(img) {
        if (!img) return;
        img.addEventListener("click", function () {
            var tag = '<img src="' + img.dataset.url + '" alt="" style="max-width:100%;">';
            var ta = document.getElementById("html_content");
            if (!ta) return;
            var start = ta.selectionStart;
            var end = ta.selectionEnd;
            ta.value = ta.value.slice(0, start) + tag + ta.value.slice(end);
            ta.focus();
            refreshPreview();
        });
    }
    qsa(".em-asset img").forEach(bindAssetClick);
})();
