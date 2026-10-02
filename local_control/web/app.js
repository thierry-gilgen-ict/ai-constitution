/* Local data only. Never interpolate server-provided strings without escaping. */
const $ = (id) => document.getElementById(id);
const escapeHTML = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const bytes = (n) =>
  Number.isFinite(n) ? (n / 1024 ** 3).toFixed(1) + " GB" : "Unknown size";
let state = null,
  inventory = null,
  authorized = false,
  refreshing = false,
  lastJobState = "",
  selectedNode = "local";
function notice(message, error = false) {
  const el = $("notice");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
}
async function api(path, body, headers = {}) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...headers },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) {
      authorized = false;
      if (!$("login").open) $("login").showModal();
    }
    throw new Error(data.error || "Request failed");
  }
  return data;
}
async function action(body) {
  try {
    await api("/api/action", body);
    notice("Operation started. Follow its progress in Overview → Activity.");
    await refresh();
  } catch (e) {
    notice(e.message, true);
  }
}
function page(name) {
  document
    .querySelectorAll(".page")
    .forEach((e) => e.classList.toggle("active", e.id === name));
  document
    .querySelectorAll(".nav")
    .forEach((e) => e.classList.toggle("active", e.dataset.page === name));
  $("breadcrumb").textContent =
    "Workspace / " +
    {
      overview: "Overview",
      models: "Model library",
      machines: "Your machines",
      connect: "Connect a project",
    }[name];
  if (name === "models") loadInventory();
}
document
  .querySelectorAll(".nav")
  .forEach((b) => b.addEventListener("click", () => page(b.dataset.page)));
$("refresh").onclick = () => {
  refresh();
  loadInventory();
  loadHardware();
};
$("work-mode").onclick = () => action({ action: "mode", mode: "work" });
$("gaming-mode").onclick = () => action({ action: "mode", mode: "gaming" });
function renderState() {
  $("connection").textContent = "● Connected locally";
  $("active-count").textContent = state.active_requests;
  $("phase").textContent =
    state.phase === "idle" ? "No responses interrupted" : state.phase;
  $("mode-badge").textContent =
    state.mode === "draining"
      ? "Finishing GPU responses"
      : state.mode === "gaming"
        ? "Gaming mode"
        : "Work mode";
  $("work-mode").classList.toggle("selected", state.mode === "work");
  $("gaming-mode").classList.toggle("selected", state.mode !== "work");
  $("route").innerHTML = ["primary", "fallback"]
    .map((role, i) => {
      const r = state[role];
      return `<div class="route-row"><span class="route-symbol">${i ? "↳" : "◉"}</span><div><small>${i ? "FALLBACK / GAMING" : "PRIMARY / WORK"}</small><strong>${r ? escapeHTML(r.source_model || r.model) : "Choose a model in your library"}</strong>${r ? `<small>${escapeHTML(state.nodes[r.node]?.name || r.node)} · ${r.cpu ? "CPU verified" : "GPU eligible"}</small>` : ""}</div></div>`;
    })
    .join("");
  $("activity").innerHTML =
    state.jobs
      .filter((j) => j.status !== "done")
      .map(
        (j) =>
          `<div class="job ${j.status === "failed" ? "failed" : ""}"><strong>${escapeHTML(j.label)}</strong><br>${escapeHTML(j.detail)}</div>`,
      )
      .join("") +
      state.events
        .slice(0, 8)
        .map(
          (e) =>
            `<div class="event"><time>${escapeHTML(e.time)}</time><span>${escapeHTML(e.message)}</span></div>`,
        )
        .join("") || '<p class="muted">Your next action will appear here.</p>';
  const latest = state.jobs.find(
    (j) => j.status === "done" && j.result?.gpu_released === false,
  );
  if (latest && state.mode === "gaming")
    notice(
      "Fallback is active, but other Ollama models still occupy GPU memory: " +
        latest.result.remaining_models.join(", "),
      true,
    );
  $("model-node").innerHTML = Object.entries(state.nodes)
    .map(
      ([id, n]) =>
        `<option value="${escapeHTML(id)}" ${id === selectedNode ? "selected" : ""}>${escapeHTML(n.name)}</option>`,
    )
    .join("");
  $("machine-list").innerHTML = Object.entries(state.nodes)
    .map(
      ([id, n]) =>
        `<article class="panel machine-card"><div class="machine-icon">${n.kind === "ollama" ? "▣" : "⌘"}</div><div><h2>${escapeHTML(n.name)}</h2><p class="muted">${escapeHTML(n.url)} · ${n.kind === "ollama" ? "Local Ollama" : "Paired HTTPS worker"}</p></div><button data-machine="${escapeHTML(id)}">Manage models ↗</button></article>`,
    )
    .join("");
  $("machine-list")
    .querySelectorAll("[data-machine]")
    .forEach(
      (b) =>
        (b.onclick = () => {
          selectedNode = b.dataset.machine;
          $("model-node").value = selectedNode;
          page("models");
        }),
    );
}
async function refresh() {
  if (!authorized || refreshing) return;
  refreshing = true;
  try {
    state = await api("/api/status");
    renderState();
    const signature = state.jobs.map((j) => j.id + j.status).join();
    if (signature !== lastJobState) {
      lastJobState = signature;
      loadInventory();
    }
  } catch (e) {
    $("connection").textContent = "Disconnected";
    notice(e.message, true);
  } finally {
    refreshing = false;
  }
}
async function loadHardware() {
  if (!authorized) return;
  try {
    const result = await api("/api/hardware");
    const h = result.system || result;
    $("gpu-memory").textContent = h.gpu_vram_gb
      ? Number(h.gpu_vram_gb).toFixed(0) + " GB"
      : "CPU only";
    $("gpu-name").textContent = h.gpu_name || "No compatible GPU detected";
    $("ram-memory").textContent = Number(h.total_ram_gb).toFixed(0) + " GB";
    $("cpu-name").textContent = h.cpu_name || "System memory";
  } catch (e) {
    $("gpu-name").textContent = "Run setup --llmfit for hardware detection";
  }
}
async function loadInventory() {
  if (!authorized) return;
  try {
    inventory = await api(
      "/api/inventory?node=" + encodeURIComponent(selectedNode),
    );
    if (selectedNode === "local")
      $("model-count").textContent = inventory.models.length;
    const running = new Map(inventory.running.map((m) => [m.name, m]));
    $("installed-models").innerHTML = inventory.models.length
      ? inventory.models
          .map((m) => {
            const r = running.get(m.name);
            return `<div class="model-row"><div class="model-info"><strong>${escapeHTML(m.name)}</strong>${r ? '<span class="tag">' + (r.size_vram ? "GPU resident" : "CPU resident") + "</span>" : ""}<small>${bytes(m.size)} on disk · ${escapeHTML(m.details?.quantization_level || "Quantization unknown")}${r ? " · " + bytes(r.size_vram) + " GPU · " + Number(r.context_length).toLocaleString() + " context" : ""}</small></div><div class="model-buttons"><button data-lifecycle="${r ? "unload" : "load"}" data-model="${escapeHTML(m.name)}">${r ? "Unload" : "Load"}</button><button data-use="${escapeHTML(m.name)}">Use in project ↗</button></div></div>`;
          })
          .join("")
      : '<p class="muted">No models yet. Find a model below or download an Ollama tag.</p>';
    $("installed-models")
      .querySelectorAll("[data-lifecycle]")
      .forEach(
        (b) =>
          (b.onclick = () =>
            action({
              action: b.dataset.lifecycle,
              node: selectedNode,
              model: b.dataset.model,
            })),
      );
    $("installed-models")
      .querySelectorAll("[data-use]")
      .forEach(
        (b) =>
          (b.onclick = () => {
            $("configure-model").value = b.dataset.use;
            $("configure-title").textContent = b.dataset.use;
            $("configure-dialog").showModal();
          }),
      );
  } catch (e) {
    $("installed-models").innerHTML =
      '<p class="muted">' +
      escapeHTML(e.message) +
      ". Start Ollama on this machine and refresh.</p>";
  }
}
$("model-node").onchange = (e) => {
  selectedNode = e.target.value;
  $("recommendations").hidden = true;
  loadInventory();
};
$("configure-cancel").onclick = () => $("configure-dialog").close();
$("configure-form").onsubmit = (e) => {
  e.preventDefault();
  $("configure-dialog").close();
  action({
    action: "configure",
    node: selectedNode,
    model: $("configure-model").value,
    role: $("configure-role").value,
    cpu: $("configure-cpu").checked,
  });
};
$("suggest").onclick = async () => {
  const button = $("suggest");
  button.disabled = true;
  button.textContent = "Checking hardware and model fit…";
  try {
    const r = await api(
      "/api/recommendations?node=" + encodeURIComponent(selectedNode),
    );
    const target = $("recommendations");
    target.hidden = false;
    target.innerHTML = `<div class="panel-head"><h2>Fits your hardware</h2><span class="tiny">${r.context.toLocaleString()} CONTEXT · 15% VRAM HEADROOM</span></div><p class="muted">${escapeHTML(r.note)}</p><div class="recommend-grid">${r.models.map((m) => `<article class="recommend-card"><h3>${escapeHTML(m.name)}</h3><p>${escapeHTML(m.best_quant)} · ${Number(m.memory_required_gb).toFixed(1)} GB estimated memory<br>${escapeHTML(m.estimated_tps)} tokens/s estimated · ${escapeHTML(m.fit_label)} fit<br>License: ${escapeHTML(m.license || "Check model card")}</p><button data-find="${escapeHTML(m.name.split("/").pop())}">Find GGUF downloads ↗</button></article>`).join("")}</div>${!r.models.length ? "<p>No coding candidates meet these constraints. Try a smaller context in a future custom profile; do not assume a larger model will fit.</p>" : ""}`;
    target.querySelectorAll("[data-find]").forEach(
      (b) =>
        (b.onclick = () => {
          $("hf-query").value = b.dataset.find;
          searchHF();
          $("hf-form").scrollIntoView({ behavior: "smooth", block: "center" });
        }),
    );
  } catch (e) {
    notice(e.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Find models for my hardware ↗";
  }
};
async function searchHF() {
  try {
    $("hf-results").textContent = "Searching public model metadata…";
    const rows = await api(
      "/api/hf/search?q=" + encodeURIComponent($("hf-query").value),
    );
    $("hf-results").innerHTML =
      rows
        .map(
          (r) =>
            `<div class="search-result"><div><a target="_blank" rel="noopener noreferrer" href="${escapeHTML(r.url)}">${escapeHTML(r.id)}</a><small class="muted"> · ${Number(r.downloads).toLocaleString()} downloads</small></div><button data-files="${escapeHTML(r.id)}">View GGUF files</button></div>`,
        )
        .join("") || '<p class="muted">No GGUF repositories found.</p>';
    $("hf-results")
      .querySelectorAll("[data-files]")
      .forEach((b) => (b.onclick = () => showFiles(b.dataset.files)));
  } catch (e) {
    notice(e.message, true);
    $("hf-results").textContent = "Search unavailable.";
  }
}
$("hf-form").onsubmit = (e) => {
  e.preventDefault();
  searchHF();
};
async function showFiles(repo) {
  try {
    const r = await api("/api/hf/files?repo=" + encodeURIComponent(repo));
    $("hf-files").innerHTML =
      `<h3>${escapeHTML(r.id)}</h3><p class="muted">License: ${escapeHTML(r.license)} · ${escapeHTML(r.note)}</p>${r.gated ? "<p>Gated repository: access must be granted by the publisher before downloading.</p>" : ""}` +
      r.files
        .slice(0, 60)
        .map(
          (f) =>
            `<div class="search-result file-row"><span>${escapeHTML(f.name)}<br><small class="muted">${bytes(f.bytes)}</small></span><button data-tag="${escapeHTML("hf.co/" + r.id + ":" + f.name)}">Select download</button></div>`,
        )
        .join("");
    $("hf-files")
      .querySelectorAll("[data-tag]")
      .forEach(
        (b) =>
          (b.onclick = () => {
            $("pull-model").value = b.dataset.tag;
            $("pull-form").scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
            notice(
              "Download selected. Review its model card and size, then click Download / update.",
            );
          }),
      );
  } catch (e) {
    notice(e.message, true);
  }
}
$("pull-form").onsubmit = (e) => {
  e.preventDefault();
  action({
    action: "pull",
    node: selectedNode,
    model: $("pull-model").value.trim(),
  });
};
$("pair-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("/api/action", {
      action: "pair",
      name: $("pair-name").value,
      code: $("pair-code").value,
    });
    $("pair-code").value = "";
    $("pair-name").value = "";
    notice("Machine paired. Its models are available in Model library.");
    await refresh();
  } catch (e) {
    notice(e.message, true);
  }
};
(async () => {
  const token = location.hash.slice(1);
  if (token) {
    history.replaceState(null, "", location.pathname);
    try {
      await api("/api/login", {}, { Authorization: "Bearer " + token });
    } catch (e) {
      notice(e.message, true);
    }
  }
  try {
    state = await api("/api/status");
    authorized = true;
    renderState();
    loadHardware();
    loadInventory();
  } catch (e) {
    if (!$("login").open) $("login").showModal();
  }
  setInterval(refresh, 2500);
})();
