(function () {
  const cfg = window.ESIGN_CONFIG || {};
  if (!cfg.pdfUrl) return;

  const pdfjsLib = window["pdfjs-dist/build/pdf"] || window.pdfjsLib;
  if (!pdfjsLib) return;
  pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.workerUrl;

  const state = {
    tool: cfg.isPublic || cfg.canManage === false ? null : "signature",
    fields: Array.isArray(cfg.fields) ? cfg.fields.map(cloneField) : [],
    selectedId: null,
    drag: null,
  };

  const pagesEl = document.getElementById("esignPages");
  const statusEl = document.getElementById("esignStatus");

  function cloneField(field) {
    return {
      id: field.id || uid(),
      type: field.type || "signature",
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
    const sizes = {
      signature: { w: 0.28, h: 0.08 },
      initials: { w: 0.1, h: 0.06 },
      date: { w: 0.16, h: 0.045 },
      text: { w: 0.26, h: 0.045 },
    };
    const size = sizes[state.tool] || sizes.signature;
    const field = {
      id: uid(),
      type: state.tool,
      page: Number(page.dataset.page),
      x: Math.max(0, Math.min(1 - size.w, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1 - size.h, (event.clientY - rect.top) / rect.height)),
      w: size.w,
      h: size.h,
      text: state.tool === "date" ? new Date().toLocaleDateString() : "",
      image: "",
    };
    state.fields.push(field);
    state.selectedId = field.id;
    renderFields();
    if (state.tool === "signature" || state.tool === "initials" || state.tool === "text") {
      openSignModal(field);
    }
  });

  function renderFields() {
    if (cfg.isSigned) return;
    document.querySelectorAll(".esign-page").forEach((page) => {
      page.querySelectorAll(".esign-field").forEach((node) => node.remove());
      const pageNo = Number(page.dataset.page);
      state.fields.filter((field) => field.page === pageNo).forEach((field) => {
        const el = document.createElement("div");
        el.className = "esign-field" + (field.id === state.selectedId ? " is-selected" : "");
        el.dataset.id = field.id;
        el.dataset.type = field.type;
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
          span.textContent = field.text || field.type;
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
          if (cfg.isPublic || field.type === "signature" || field.type === "initials") {
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

  function openSignModal(field) {
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
    showSignTab("draw");
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

  document.getElementById("esignApplyMark")?.addEventListener("click", () => {
    if (!activeField) return;
    const tab = document.querySelector("[data-sign-tab].is-active")?.getAttribute("data-sign-tab");
    if (tab === "draw" && pad) {
      activeField.image = pad.toDataURL("image/png");
      activeField.text = "";
    } else if (tab === "type") {
      activeField.text = (typeInput?.value || "").trim();
      activeField.image = "";
    } else if (tab === "saved" && cfg.savedSignature) {
      activeField.image = cfg.savedSignature;
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

  document.getElementById("esignFinish")?.addEventListener("click", async () => {
    if (!state.fields.length) {
      setStatus("Place at least one signature field.");
      return;
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
      setStatus("Place the signature boxes first, then send.");
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
      setStatus("Click a yellow box to sign, then Finish.");
    } else if (isReadOnly()) {
      setStatus("View only.");
    } else {
      setStatus("Click the page to place a signature, like Acrobat Fill & Sign.");
    }
  }

  renderPdf().catch(() => setStatus("Could not open this PDF in the browser."));
})();
