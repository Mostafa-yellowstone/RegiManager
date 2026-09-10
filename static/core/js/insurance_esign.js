(function () {
  const cfg = window.ESIGN_CONFIG || {};
  if (!cfg.pdfUrl) return;

  const pdfjsLib = window["pdfjs-dist/build/pdf"] || window.pdfjsLib;
  if (!pdfjsLib) return;
  pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.workerUrl;

  const state = {
    tool: cfg.isPublic || cfg.canManage === false ? null : "agent-signature",
    fields: Array.isArray(cfg.fields) ? cfg.fields.map(cloneField) : [],
    selectedId: null,
    drag: null,
  };

  const pagesEl = document.getElementById("esignPages");
  const statusEl = document.getElementById("esignStatus");

  function fieldRole(field) {
    return field && field.role === "agent" ? "agent" : "client";
  }

  function fieldLabel(field) {
    if (field.text) return field.text;
    if (field.type === "signature") {
      return fieldRole(field) === "agent" ? "Agent sign" : "Client sign";
    }
    if (field.type === "initials") {
      return fieldRole(field) === "agent" ? "Agent initials" : "Client initials";
    }
    return field.type || "field";
  }

  function toolSpec(tool) {
    const map = {
      "agent-signature": { type: "signature", role: "agent", openModal: true },
      "client-signature": { type: "signature", role: "client", openModal: false },
      initials: { type: "initials", role: "client", openModal: true },
      date: { type: "date", role: "client", openModal: false },
      text: { type: "text", role: "client", openModal: true },
      signature: { type: "signature", role: "client", openModal: true },
    };
    return map[tool] || map["client-signature"];
  }

  function cloneField(field) {
    return {
      id: field.id || uid(),
      type: field.type || "signature",
      role: field.role === "agent" ? "agent" : "client",
      page: Number(field.page || 1),
      x: Number(field.x || 0),
      y: Number(field.y || 0),
      w: Number(field.w || 0.24),
      h: Number(field.h || 0.07),
      text: field.text || "",
      image: field.image || "",
    };
  }

  function uid() {
    return "f" + Math.random().toString(36).slice(2, 10);
  }

  function csrf() {
    return cfg.csrf || document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function isReadOnly() {
    return !!cfg.isSigned || (!cfg.isPublic && cfg.canManage === false);
  }

  document.querySelectorAll("[data-esign-tool]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tool = btn.getAttribute("data-esign-tool");
      document.querySelectorAll("[data-esign-tool]").forEach((other) => {
        other.classList.toggle("is-active", other === btn);
      });
    });
  });

  pagesEl.addEventListener("click", (event) => {
    if (isReadOnly()) return;
    const page = event.target.closest(".esign-page");
    if (!page || event.target.closest(".esign-field")) return;
    if (cfg.isPublic) return;
    if (!state.tool) return;
    const rect = page.getBoundingClientRect();
    const spec = toolSpec(state.tool);
    const sizes = {
      signature: { w: 0.28, h: 0.08 },
      initials: { w: 0.1, h: 0.06 },
      date: { w: 0.16, h: 0.045 },
      text: { w: 0.26, h: 0.045 },
    };
    const size = sizes[spec.type] || sizes.signature;
    const field = {
      id: uid(),
      type: spec.type,
      role: spec.role,
      page: Number(page.dataset.page),
      x: Math.max(0, Math.min(1 - size.w, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1 - size.h, (event.clientY - rect.top) / rect.height)),
      w: size.w,
      h: size.h,
      text: spec.type === "date" ? new Date().toLocaleDateString() : "",
      image: "",
    };
    state.fields.push(field);
    state.selectedId = field.id;
    renderFields();
    if (spec.openModal) {
      openSignModal(field);
    } else if (spec.role === "client" && spec.type === "signature") {
      setStatus("Client signature box placed — the customer will sign here.");
    }
  });

  function renderFields() {
    if (cfg.isSigned) return;
    document.querySelectorAll(".esign-page").forEach((page) => {
      page.querySelectorAll(".esign-field").forEach((node) => node.remove());
      const pageNo = Number(page.dataset.page);
      state.fields.filter((field) => field.page === pageNo).forEach((field) => {
        const role = fieldRole(field);
        const lockedForClient = cfg.isPublic && role === "agent";
        const el = document.createElement("div");
        el.className =
          "esign-field" +
          (field.id === state.selectedId ? " is-selected" : "") +
          (lockedForClient ? " is-locked" : "");
        el.dataset.id = field.id;
        el.dataset.type = field.type;
        el.dataset.role = role;
        el.style.left = field.x * 100 + "%";
        el.style.top = field.y * 100 + "%";
        el.style.width = field.w * 100 + "%";
        el.style.height = field.h * 100 + "%";
        if (field.image) {
          const img = document.createElement("img");
          img.src = field.image;
          el.appendChild(img);
        } else {
          const span = document.createElement("span");
          span.textContent = fieldLabel(field);
          el.appendChild(span);
        }
        if (!isReadOnly() && !cfg.isPublic) {
          const handle = document.createElement("div");
          handle.className = "esign-resize";
          el.appendChild(handle);
        }
        el.addEventListener("mousedown", onFieldDown);
        el.addEventListener("click", (event) => {
          event.stopPropagation();
          if (isReadOnly()) return;
          state.selectedId = field.id;
          renderFields();
          if (lockedForClient) {
            setStatus("Agent signature is locked. Sign only in the yellow Client sign boxes.");
            return;
          }
          if (cfg.isPublic || field.type === "signature" || field.type === "initials" || field.type === "text") {
            openSignModal(field);
          }
        });
        page.appendChild(el);
      });
    });
  }

  function onFieldDown(event) {
    if (isReadOnly() || cfg.isPublic) return;
    const el = event.currentTarget;
    const field = state.fields.find((row) => row.id === el.dataset.id);
    if (!field) return;
    state.selectedId = field.id;
    const page = el.closest(".esign-page");
    const rect = page.getBoundingClientRect();
    const resizing = event.target.classList.contains("esign-resize");
    state.drag = {
      field,
      resizing,
      startX: event.clientX,
      startY: event.clientY,
      orig: { x: field.x, y: field.y, w: field.w, h: field.h },
      rect,
    };
    event.preventDefault();
  }

  window.addEventListener("mousemove", (event) => {
    if (!state.drag) return;
    const { field, resizing, startX, startY, orig, rect } = state.drag;
    const dx = (event.clientX - startX) / rect.width;
    const dy = (event.clientY - startY) / rect.height;
    if (resizing) {
      field.w = Math.max(0.06, Math.min(0.8, orig.w + dx));
      field.h = Math.max(0.03, Math.min(0.4, orig.h + dy));
    } else {
      field.x = Math.max(0, Math.min(1 - field.w, orig.x + dx));
      field.y = Math.max(0, Math.min(1 - field.h, orig.y + dy));
    }
    renderFields();
  });
  window.addEventListener("mouseup", () => { state.drag = null; });

  window.addEventListener("keydown", (event) => {
    if (isReadOnly() || cfg.isPublic) return;
    if ((event.key === "Delete" || event.key === "Backspace") && state.selectedId && !event.target.matches("input,textarea")) {
      state.fields = state.fields.filter((field) => field.id !== state.selectedId);
      state.selectedId = null;
      renderFields();
    }
  });

  let activeField = null;
  const modal = document.getElementById("esignModal");
  const pad = document.getElementById("esignPad");
  const typeInput = document.getElementById("esignTypeInput");
  let drawing = false;
  let savedSignatures = Array.isArray(cfg.savedSignatures) ? cfg.savedSignatures.slice() : [];
  let selectedSavedId = null;
  let uploadedImageDataUrl = "";

  function setSaveHint(message, isError) {
    const hint = document.getElementById("esignSaveHint");
    if (!hint) return;
    if (!message) {
      hint.hidden = true;
      hint.textContent = "";
      hint.classList.remove("is-error");
      return;
    }
    hint.hidden = false;
    hint.textContent = message;
    hint.classList.toggle("is-error", !!isError);
  }

  function clearUploadPreview() {
    uploadedImageDataUrl = "";
    const input = document.getElementById("esignUploadInput");
    const preview = document.getElementById("esignUploadPreview");
    const img = document.getElementById("esignUploadPreviewImg");
    if (input) input.value = "";
    if (img) img.removeAttribute("src");
    if (preview) preview.hidden = true;
  }

  function setUploadPreview(dataUrl) {
    uploadedImageDataUrl = dataUrl || "";
    const preview = document.getElementById("esignUploadPreview");
    const img = document.getElementById("esignUploadPreviewImg");
    if (!uploadedImageDataUrl) {
      clearUploadPreview();
      return;
    }
    if (img) img.src = uploadedImageDataUrl;
    if (preview) preview.hidden = false;
  }

  function readImageFile(file) {
    return new Promise((resolve, reject) => {
      if (!file) {
        reject(new Error("Choose an image file."));
        return;
      }
      const allowed = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"];
      if (file.type && !allowed.includes(file.type)) {
        reject(new Error("Use a PNG, JPG, WEBP, or GIF image."));
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        reject(new Error("That image is larger than 2 MB."));
        return;
      }
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Could not read that image."));
      reader.readAsDataURL(file);
    });
  }

  async function saveNamedSignature(name, image) {
    if (!cfg.saveSignatureUrl) throw new Error("Saving is unavailable.");
    const data = await postJson(cfg.saveSignatureUrl, { name, image });
    savedSignatures = Array.isArray(data.signatures) ? data.signatures : [];
    if (data.signature && data.signature.id != null) {
      selectedSavedId = data.signature.id;
    }
    renderSavedSignatures();
    return data;
  }

  function renderSavedSignatures() {
    const grid = document.getElementById("esignSavedGrid");
    const empty = document.getElementById("esignSavedEmpty");
    if (!grid) return;
    grid.innerHTML = "";
    if (!savedSignatures.length) {
      if (empty) empty.hidden = false;
      selectedSavedId = null;
      return;
    }
    if (empty) empty.hidden = true;
    if (!selectedSavedId || !savedSignatures.some((row) => String(row.id) === String(selectedSavedId))) {
      selectedSavedId = savedSignatures[0].id;
    }
    savedSignatures.forEach((row) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "esign-saved-card" + (String(row.id) === String(selectedSavedId) ? " is-selected" : "");
      card.setAttribute("data-saved-id", String(row.id));
      card.innerHTML =
        '<span class="esign-saved-card__preview"><img alt=""></span>' +
        '<span class="esign-saved-card__meta">' +
          '<strong></strong>' +
          (row.is_profile ? '<em>From profile</em>' : '<em>Saved signature</em>') +
        "</span>" +
        (row.can_delete
          ? '<span class="esign-saved-card__delete" data-delete-id="' + String(row.id) + '" title="Delete">×</span>'
          : "");
      const img = card.querySelector("img");
      const title = card.querySelector("strong");
      if (img) img.src = row.image || "";
      if (title) title.textContent = row.name || "Signature";
      card.addEventListener("click", (event) => {
        if (event.target.closest("[data-delete-id]")) return;
        selectedSavedId = row.id;
        renderSavedSignatures();
      });
      const del = card.querySelector("[data-delete-id]");
      if (del) {
        del.addEventListener("click", async (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (!cfg.deleteSignatureUrlTemplate) return;
          if (!window.confirm('Delete saved signature "' + (row.name || "") + '"?')) return;
          try {
            const url = cfg.deleteSignatureUrlTemplate.replace("{id}", String(row.id));
            const data = await postJson(url, {});
            savedSignatures = Array.isArray(data.signatures) ? data.signatures : [];
            selectedSavedId = null;
            renderSavedSignatures();
            setSaveHint('Deleted "' + (row.name || "signature") + '".');
          } catch (err) {
            setSaveHint(err.message || "Could not delete signature.", true);
          }
        });
      }
      grid.appendChild(card);
    });
  }

  function openSignModal(field) {
    if (cfg.isPublic && fieldRole(field) === "agent") {
      setStatus("Agent signature is locked. Sign only in the yellow Client sign boxes.");
      return;
    }
    activeField = field;
    if (!modal) return;
    modal.classList.add("is-open");
    if (typeInput) typeInput.value = field.text || cfg.signerName || "";
    if (pad) {
      const ctx = pad.getContext("2d");
      ctx.clearRect(0, 0, pad.width, pad.height);
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, pad.width, pad.height);
    }
    setSaveHint("");
    clearUploadPreview();
    const uploadName = document.getElementById("esignUploadSaveName");
    if (uploadName) uploadName.value = "";
    renderSavedSignatures();
    const preferred = (!cfg.isPublic && savedSignatures.length) ? "saved" : "draw";
    showSignTab(preferred);
  }

  function closeModal() {
    modal?.classList.remove("is-open");
    activeField = null;
  }

  function showSignTab(name) {
    document.querySelectorAll("[data-sign-tab]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-sign-tab") === name);
    });
    document.querySelectorAll("[data-sign-panel]").forEach((panel) => {
      panel.style.display = panel.getAttribute("data-sign-panel") === name ? "block" : "none";
    });
  }

  document.querySelectorAll("[data-sign-tab]").forEach((btn) => {
    btn.addEventListener("click", () => showSignTab(btn.getAttribute("data-sign-tab")));
  });
  document.getElementById("esignModalClose")?.addEventListener("click", closeModal);

  if (pad) {
    const ctx = pad.getContext("2d");
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#0f172a";
    const pos = (event) => {
      const rect = pad.getBoundingClientRect();
      const src = event.touches ? event.touches[0] : event;
      return {
        x: (src.clientX - rect.left) * (pad.width / rect.width),
        y: (src.clientY - rect.top) * (pad.height / rect.height),
      };
    };
    const start = (event) => { drawing = true; const p = pos(event); ctx.beginPath(); ctx.moveTo(p.x, p.y); event.preventDefault(); };
    const move = (event) => { if (!drawing) return; const p = pos(event); ctx.lineTo(p.x, p.y); ctx.stroke(); event.preventDefault(); };
    const end = () => { drawing = false; };
    pad.addEventListener("mousedown", start);
    pad.addEventListener("mousemove", move);
    window.addEventListener("mouseup", end);
    pad.addEventListener("touchstart", start, { passive: false });
    pad.addEventListener("touchmove", move, { passive: false });
    pad.addEventListener("touchend", end);
    document.getElementById("esignPadClear")?.addEventListener("click", () => {
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, pad.width, pad.height);
    });
  }

  document.getElementById("esignSaveCurrent")?.addEventListener("click", async () => {
    if (!pad || !cfg.saveSignatureUrl) return;
    const nameInput = document.getElementById("esignSaveName");
    const name = (nameInput?.value || "").trim();
    if (!name) {
      setSaveHint("Enter a name for this signature.", true);
      nameInput?.focus();
      return;
    }
    try {
      await saveNamedSignature(name, pad.toDataURL("image/png"));
      if (nameInput) nameInput.value = "";
      setSaveHint('Saved as "' + name + '". You can reuse it from the Saved tab.');
      showSignTab("saved");
    } catch (err) {
      setSaveHint(err.message || "Could not save signature.", true);
    }
  });

  const uploadInput = document.getElementById("esignUploadInput");
  const uploadDrop = document.querySelector(".esign-upload-drop");
  uploadDrop?.addEventListener("dragover", (event) => {
    event.preventDefault();
    uploadDrop.classList.add("is-dragging");
  });
  uploadDrop?.addEventListener("dragleave", () => uploadDrop.classList.remove("is-dragging"));
  uploadDrop?.addEventListener("drop", async (event) => {
    event.preventDefault();
    uploadDrop.classList.remove("is-dragging");
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await readImageFile(file);
      setUploadPreview(dataUrl);
      setSaveHint("Image ready. Name it and save, or Apply to use it now.");
    } catch (err) {
      clearUploadPreview();
      setSaveHint(err.message || "Could not upload that image.", true);
    }
  });
  uploadInput?.addEventListener("change", async () => {
    const file = uploadInput.files && uploadInput.files[0];
    if (!file) return;
    try {
      const dataUrl = await readImageFile(file);
      setUploadPreview(dataUrl);
      setSaveHint("Image ready. Name it and save, or Apply to use it now.");
    } catch (err) {
      clearUploadPreview();
      setSaveHint(err.message || "Could not upload that image.", true);
    }
  });
  document.getElementById("esignUploadClear")?.addEventListener("click", () => {
    clearUploadPreview();
    setSaveHint("");
  });
  document.getElementById("esignUploadSave")?.addEventListener("click", async () => {
    if (!cfg.saveSignatureUrl) return;
    if (!uploadedImageDataUrl) {
      setSaveHint("Choose an image to upload first.", true);
      return;
    }
    const nameInput = document.getElementById("esignUploadSaveName");
    const name = (nameInput?.value || "").trim();
    if (!name) {
      setSaveHint("Enter a name for this signature.", true);
      nameInput?.focus();
      return;
    }
    try {
      await saveNamedSignature(name, uploadedImageDataUrl);
      if (nameInput) nameInput.value = "";
      clearUploadPreview();
      setSaveHint('Uploaded and saved as "' + name + '".');
      showSignTab("saved");
    } catch (err) {
      setSaveHint(err.message || "Could not save uploaded signature.", true);
    }
  });

  document.getElementById("esignApplyMark")?.addEventListener("click", () => {
    if (!activeField) return;
    if (cfg.isPublic && fieldRole(activeField) === "agent") {
      setStatus("Agent signature is locked.");
      closeModal();
      return;
    }
    const tab = document.querySelector("[data-sign-tab].is-active")?.getAttribute("data-sign-tab");
    if (tab === "draw" && pad) {
      activeField.image = pad.toDataURL("image/png");
      activeField.text = "";
    } else if (tab === "type") {
      activeField.text = (typeInput?.value || "").trim();
      activeField.image = "";
    } else if (tab === "upload") {
      if (!uploadedImageDataUrl) {
        setSaveHint("Upload a signature image first.", true);
        return;
      }
      activeField.image = uploadedImageDataUrl;
      activeField.text = "";
    } else if (tab === "saved") {
      const chosen = savedSignatures.find((row) => String(row.id) === String(selectedSavedId));
      const image = (chosen && chosen.image) || cfg.savedSignature || "";
      if (!image) {
        setSaveHint("Select a saved signature first.", true);
        return;
      }
      activeField.image = image;
      activeField.text = "";
    }
    renderFields();
    closeModal();
  });

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({ ok: false, error: "Request failed." }));
    if (!response.ok || !data.ok) throw new Error(data.error || data.message || "Request failed.");
    return data;
  }

  function payload() {
    return {
      fields: state.fields,
      signer_name: document.getElementById("esignSignerName")?.value || cfg.signerName || "",
      signer_email: document.getElementById("esignSignerEmail")?.value || "",
    };
  }

  function hasMark(field) {
    return !!(field.image || ((field.type === "signature" || field.type === "initials" || field.type === "text" || field.type === "date") && (field.text || "").trim()));
  }

  function validateRequestReady() {
    const agentOk = state.fields.some(
      (f) => fieldRole(f) === "agent" && (f.type === "signature" || f.type === "initials") && hasMark(f)
    );
    const clientOk = state.fields.some(
      (f) => fieldRole(f) === "client" && (f.type === "signature" || f.type === "initials")
    );
    if (!agentOk) return "Place and complete your Agent signature first.";
    if (!clientOk) return "Place at least one Client signature box for the customer.";
    return "";
  }

  function validatePublicReady() {
    const clientBoxes = state.fields.filter(
      (f) => fieldRole(f) === "client" && (f.type === "signature" || f.type === "initials")
    );
    if (clientBoxes.length) {
      if (clientBoxes.some((f) => !hasMark(f))) {
        return "Sign every yellow Client sign box before finishing.";
      }
      return "";
    }
    if (!state.fields.some((f) => (f.type === "signature" || f.type === "initials") && hasMark(f))) {
      return "Click each signature field and sign before finishing.";
    }
    return "";
  }

  document.getElementById("esignFinish")?.addEventListener("click", async () => {
    if (!state.fields.length) {
      setStatus("Place at least one signature field.");
      return;
    }
    if (cfg.isPublic) {
      const publicError = validatePublicReady();
      if (publicError) {
        setStatus(publicError);
        return;
      }
    }
    setStatus("Applying signature…");
    try {
      const data = await postJson(cfg.applyUrl, payload());
      setStatus("Signed.");
      if (data.download) window.open(data.download, "_blank");
      if (cfg.isPublic) {
        window.location.reload();
      } else if (data.redirect) {
        window.location.href = data.redirect;
      }
    } catch (err) {
      setStatus(err.message);
    }
  });

  document.getElementById("esignRequest")?.addEventListener("click", async () => {
    if (!state.fields.length) {
      setStatus("Place Agent and Client signature boxes first, then send.");
      return;
    }
    const requestError = validateRequestReady();
    if (requestError) {
      setStatus(requestError);
      return;
    }
    const email = (document.getElementById("esignSignerEmail")?.value || "").trim();
    if (!email) {
      setStatus("Enter the signer email address to send the request.");
      document.getElementById("esignSignerEmail")?.focus();
      return;
    }
    setStatus("Sending signature request to " + email + "…");
    try {
      const data = await postJson(cfg.requestUrl, payload());
      if (data.link) {
        await navigator.clipboard.writeText(data.link).catch(() => {});
      }
      setStatus((data.message || "Email sent.") + " Link also copied.");
    } catch (err) {
      setStatus(err.message);
    }
  });

  async function renderPdf() {
    setStatus("Loading PDF…");
    const pdf = await pdfjsLib.getDocument({ url: cfg.pdfUrl, withCredentials: true }).promise;
    pagesEl.innerHTML = "";
    for (let n = 1; n <= pdf.numPages; n += 1) {
      const page = await pdf.getPage(n);
      const viewport = page.getViewport({ scale: 1.25 });
      const wrap = document.createElement("div");
      wrap.className = "esign-page" + (isReadOnly() ? " is-readonly" : "");
      wrap.dataset.page = String(n);
      wrap.style.width = viewport.width + "px";
      wrap.style.height = viewport.height + "px";
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      wrap.appendChild(canvas);
      pagesEl.appendChild(wrap);
    }
    renderFields();
    if (cfg.isSigned) {
      setStatus("Signed document — the signature is on the page. Use Download if you need a copy.");
    } else if (cfg.isPublic) {
      setStatus("Teal Agent signature is locked. Click a yellow Client sign box to draw or type your signature, then Finish.");
    } else if (isReadOnly()) {
      setStatus("View only.");
    } else {
      setStatus("Place your Agent signature (and sign it), then place a Client signature box and Request signature.");
    }
  }

  renderPdf().catch(() => setStatus("Could not open this PDF in the browser."));
})();
