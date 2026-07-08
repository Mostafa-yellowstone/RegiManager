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
