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
let driversRequested = false, driverTarget = null;
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
    const result = await api("/api/action", body);
    notice(result.job ? "Operation started. Follow its progress in Overview → Activity." : (result.note || result.applies || "Updated."));
    await refresh();
  } catch (e) {
    notice(e.message, true);
  }
}
function page(name) {
  window.scrollTo({top: 0, behavior: 'instant'});
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
      setup: "Get started",
      architectures: "Project templates",
      constitution: "Constitution files",
      projects: "Project sync", accounts: "Apps & subscriptions", workers: "Set up a worker", storage: "Storage & locations", vault: "Configs & backups",
    }[name];
  if (name === "models") loadInventory();
  if (name === "setup") loadSetup();
  if (window.studioPage) window.studioPage(name);
  if (window.centerPage) window.centerPage(name);
  if (name === "machines" && !driversRequested) {
    driversRequested = true;
    action({action: "driver-check-all"});
  }
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
  $("session-status").textContent = `${(state.sessions || []).filter(s => s.status === "open").length} open managed sessions · ${state.queued_requests || 0} queued requests. Interrupted operations remain visible below.`;
  $("gaming-mode").disabled = !state.primary || !state.fallback || state.phase !== "idle";
  $("work-mode").disabled = !state.primary || state.phase !== "idle";
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
    (state.waiting_requests || []).map(id => `<div class="job">Queued request ${escapeHTML(id)} <button data-request="${escapeHTML(id)}">Cancel request</button></div>`).join("") + state.jobs
      .filter((j) => j.status !== "done")
      .map(
        (j) =>
          `<div class="job ${["failed", "interrupted"].includes(j.status) ? "failed" : ""}"><strong>${escapeHTML(j.label)} · ${escapeHTML(j.status)}</strong><br>${escapeHTML(j.detail)}${j.status === "queued" || (j.status === "running" && j.operation === "pull") ? `<button data-cancel="${escapeHTML(j.id)}">Cancel</button>` : ""}</div>`,
      )
      .join("") +
      state.events
        .slice(0, 8)
        .map(
          (e) =>
            `<div class="event"><time>${escapeHTML(e.time)}</time><span>${escapeHTML(e.message)}</span></div>`,
        )
        .join("") || '<p class="muted">Your next action will appear here.</p>';
  $("activity").querySelectorAll("[data-request]").forEach(b => b.onclick = () => action({action:"cancel-request",request:b.dataset.request}));
  $("activity").querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => action({action: "cancel", job: b.dataset.cancel}));
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
        `<article class="panel machine-card"><div class="machine-icon">${n.kind === "ollama" ? "▣" : "⌘"}</div><div><h2>${escapeHTML(n.name)}</h2><p class="muted">${escapeHTML(n.url)} · ${escapeHTML(state.health?.[id]?.status || "Health not checked")} ${escapeHTML(state.health?.[id]?.version || "")} · ${n.kind === "ollama" ? "Local Ollama" : "Paired HTTPS worker"}</p></div><div class="button-row"><button data-machine="${escapeHTML(id)}">Manage models ↗</button>${`<button data-maintenance="${escapeHTML(id)}">${state.maintenance.includes(id) ? "Leave maintenance" : "Drain for maintenance"}</button>`}${`<button data-eligible="${escapeHTML(id)}">${n.gaming_eligible === false ? "Allow for Gaming" : "Exclude from Gaming"}</button>`}${n.kind === "worker" ? `<button data-rotate="${escapeHTML(id)}">Rotate credentials</button><button data-remove="${escapeHTML(id)}">Revoke &amp; remove</button>` : ""}</div>${driverPanel(id, n)}</article>`,
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
  $("fallback-order").textContent = [state.fallback, ...(state.fallbacks || [])].filter(Boolean).filter((r,i,a) => a.findIndex(v => v.node === r.node && v.model === r.model) === i).map(r => `${state.nodes[r.node]?.name || r.node}: ${r.source_model || r.model}`).join(" → ") || "Configure a fallback in Model library.";
  $("health-history").textContent = (state.health_history || []).slice(-8).reverse().map(v => `${new Date(v.checked_at * 1000).toLocaleTimeString()} · ${state.nodes[v.node]?.name || "Removed machine"} · ${v.status}${v.version ? " · Ollama " + v.version : ""}`).join("\n") || "No health observations yet. Use Check machines in Overview.";
  if (document.activeElement !== $("routing-policy")) $("routing-policy").value = state.routing_policy || "configured";
  $("machine-list").querySelectorAll("[data-eligible]").forEach(b => b.onclick = () => action({action:"routing-policy",preference:state.routing_policy,node:b.dataset.eligible,eligible:state.nodes[b.dataset.eligible].gaming_eligible === false}));
  $("machine-list").querySelectorAll("[data-maintenance]").forEach(b => b.onclick = () => action({action:"maintenance",node:b.dataset.maintenance,enabled:!state.maintenance.includes(b.dataset.maintenance)}));
  $("machine-list").querySelectorAll("[data-rotate]").forEach(b => b.onclick = () => action({action:"rotate-node",node:b.dataset.rotate}));
  $("machine-list").querySelectorAll("[data-remove]").forEach(b => b.onclick = () => action({action:"remove-node",node:b.dataset.remove}));
  $("machine-list").querySelectorAll("[data-driver-check]").forEach(b => b.onclick = () => action({action:"driver-check",node:b.dataset.driverCheck,updates:b.dataset.updates === "true"}));
  $("machine-list").querySelectorAll("[data-driver-update]").forEach(b => b.onclick = () => openDriverDialog(b.dataset.driverUpdate));
  $("machine-list").querySelectorAll("[data-driver-resume]").forEach(b => b.onclick = () => action({action:"driver-resume",node:b.dataset.driverResume}));
}
function driverPanel(id, node) {
  if (id !== "local" && node.kind === "ollama") return '<div class="driver-panel"><p class="caption">Shares this computer’s display drivers. Driver maintenance pauses both GPU and CPU runtimes.</p></div>';
  const d = state.drivers?.[id], e = escapeHTML, paused = (state.driver_paused || []).includes(id);
  const busy = state.jobs.some(j => ["queued", "running"].includes(j.status) && j.operation?.startsWith("driver_"));
  const labels = {ok:"Versions detected", unavailable:"Check unavailable", "worker-upgrade":"Worker update needed", empty:"No adapters reported", unsupported:"OS not supported"};
  const u = d?.updates || {}, updateLabels = {"not-checked":"Update availability not checked", available:"Windows offers display-driver updates", "none-offered":"No display drivers offered by Windows Update", unavailable:"Update check unavailable", manual:"Check releases in the native updater"};
  return `<div class="driver-panel"><div class="driver-heading"><h3>Display drivers</h3><span class="tag">${busy ? "Checking / preparing…" : e(labels[d?.status] || "Not checked yet")}</span></div>
    ${d?.adapters?.length ? '<div class="driver-list">' + d.adapters.map(a => `<div class="driver-row"><div><strong>${e(a.name)}</strong><small>${e(a.vendor || "Provider unknown")}${a.virtual ? " · Virtual display" : ""}${a.component ? " · " + e(a.component) : ""}</small></div><div class="driver-version"><strong>${e(a.version || "Version unavailable")}</strong><small>${a.version_kind ? e(a.version_kind) + " version" : a.date ? "Driver date · " + e(a.date) : "Driver date unavailable"}</small></div></div>`).join("") + '</div>' : '<p class="muted">' + e(d?.note || "Read the installed display-driver versions without loading a model.") + '</p>'}
    ${d?.checked_at ? `<p class="caption">Observed ${e(new Date(d.checked_at * 1000).toLocaleString())} · ${e(d.source || "Worker inventory")}${d.os_version ? " · " + e(d.platform) + " " + e(d.os_version) : ""}</p>` : ""}
    ${d?.adapters?.length ? `<p class="caption">${e(d.note)}</p>` : ""}
    ${d?.reboot_pending ? '<p class="driver-alert">Windows reports a pending restart. Review it on this computer before resuming model work.</p>' : ""}
    ${(d?.changes || []).map(c => `<p class="driver-change">Version changed: ${e(c.name)} · ${e(c.before)} → ${e(c.after)}. Model stability still needs verification.</p>`).join("")}
    ${d?.status === "ok" ? `<div class="driver-update-status"><strong>${e(updateLabels[u.status] || "Update status unknown")}</strong>${u.checked_at ? `<small>Checked ${e(new Date(u.checked_at * 1000).toLocaleString())}</small>` : ""}${(u.offers || []).map(o => `<p>${e(o.title)}</p>`).join("")}<p class="caption">${e(u.note || "A version or driver date alone cannot establish whether this GPU has a newer compatible release.")}</p></div>` : ""}
    ${paused ? '<p class="driver-alert">Paused for driver maintenance. Finish on this computer’s desktop, then refresh and resume. Restarting Local Control keeps this pause.</p>' : ""}
    ${d?.handoff && paused ? `<p class="caption">${e(d.handoff.note)}</p>` : ""}
    <div class="button-row"><button data-driver-check="${e(id)}" ${busy ? "disabled" : ""}>Refresh versions</button>${d?.status === "ok" && d.platform === "Windows" ? `<button data-driver-check="${e(id)}" data-updates="true" ${busy ? "disabled" : ""}>Check Windows updates</button>` : ""}${d?.actions?.length ? `<button data-driver-update="${e(id)}" ${busy ? "disabled" : ""}>Update drivers ↗</button>` : ""}${paused ? `<button data-driver-resume="${e(id)}" ${busy ? "disabled" : ""}>Recheck &amp; resume model use</button>` : ""}</div>
    ${d?.platform === "Linux" && !d.actions?.length ? '<p class="caption">No supported desktop updater found. Use this distribution’s package tools on the machine; automatic privileged installation is unavailable.</p>' : ""}
  </div>`;
}
function openDriverDialog(id) {
  driverTarget = id;
  $("driver-target").textContent = "Update controls will open on " + state.nodes[id].name + ".";
  $("driver-action").innerHTML = state.drivers[id].actions.map(a => `<option value="${escapeHTML(a.id)}">${escapeHTML(a.label)}</option>`).join("");
  $("driver-action").onchange();
  $("driver-ack").checked = false;
  $("driver-dialog").showModal();
}
$("driver-action").onchange = () => {
  $("driver-action-detail").textContent = state.drivers[driverTarget].actions.find(a => a.id === $("driver-action").value)?.detail || "";
};
$("driver-cancel").onclick = () => $("driver-dialog").close();
$("driver-form").onsubmit = e => {
  e.preventDefault();
  $("driver-dialog").close();
  action({action:"driver-update", node:driverTarget, target:$("driver-action").value, acknowledge_external:$("driver-ack").checked});
};
$("refresh-drivers").onclick = () => action({action:"driver-check-all"});
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
      if ($("setup").classList.contains("active")) loadSetup();
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
let supportReport = null;
$("evaluate-primary").onclick = () => action({action:"benchmark", role:"primary"});
$("evaluate-fallback").onclick = () => action({action:"benchmark", role:"fallback"});
$("show-evaluations").onclick = async () => {
  try {
    const rows = await api("/api/evaluations");
    $("evaluation-results").innerHTML = rows.map(r => `<article class="model-row"><div><strong>${escapeHTML(r.model)}</strong><p>${escapeHTML(r.level)} · ${escapeHTML(r.status)}${r.stale ? " · stale or unavailable" : ""}</p><small>${r.coding ? `${r.coding.passed}/${r.coding.total} fixture checks · ` : ""}${r.first_text_seconds ?? "—"}s to first text · ${r.output_tokens_per_second ?? "—"} output tokens/s over total request time · ${escapeHTML(r.quantization || "Unknown quantization")}${r.memory ? ` · ${bytes(r.memory.peak_gpu_bytes_sampled)} peak sampled model GPU allocation (${r.memory.samples} observations)` : " · Peak allocation not sampled in this earlier result"}</small></div></article>`).join("") || "<p>No measurements yet. Start with a configured route.</p>";
  } catch (e) { notice(e.message, true); }
};
async function loadSetup() {
  if (!authorized) return;
  try {
    const setup = await api("/api/setup");
    $("setup-summary").textContent = `${setup.inventory.version ? "Ollama " + setup.inventory.version + " is running" : "Start Ollama to continue"} · ${bytes(setup.disk_free_bytes)} free on the configuration volume · ${setup.primary_ready ? "Primary ready" : "Primary needed"} · ${setup.fallback_ready ? "Fallback ready" : "Fallback needed"}`;
    $("setup-context").value = String(setup.context);
    $("setup-context").disabled = setup.primary_ready || setup.fallback_ready;
    $("save-context").disabled = setup.primary_ready || setup.fallback_ready;
    $("suggest-context").disabled = setup.primary_ready || setup.fallback_ready;
    $("setup-ollama").disabled = setup.ollama;
    $("setup-ollama").textContent = setup.ollama ? "Ollama installed" : "Install Ollama";
    $("setup-fit").disabled = setup.llmfit;
    $("setup-fit").textContent = setup.llmfit ? "Hardware helper installed" : "Install hardware helper";
    const selected = $("setup-model").value;
    $("setup-model").innerHTML = setup.inventory.models.filter(m => !m.name.startsWith("constitution-")).map(m => `<option value="${escapeHTML(m.name)}">${escapeHTML(m.name)} · ${bytes(m.size)}</option>`).join("");
    if ([...$("setup-model").options].some(o => o.value === selected)) $("setup-model").value = selected;
    $("setup-primary").disabled = !$("setup-model").value;
    $("setup-fallback").disabled = !$("setup-model").value;
  } catch (e) { notice(e.message, true); }
}
$("suggest-context").onclick = async () => {
  try { const advice = await api("/api/context-advice"); $("setup-context").value = String(advice.suggested); notice(`${advice.suggested.toLocaleString()} context suggested. ${advice.reason} Click Save context to apply.`); } catch(e) { notice(e.message,true); }
};
$("save-routing-policy").onclick = () => action({action:"routing-policy",preference:$("routing-policy").value});
$("setup-ollama").onclick = () => action({action:"setup", component:"ollama"});
$("setup-fit").onclick = () => action({action:"setup", component:"llmfit"});
$("save-context").onclick = () => action({action:"context", context:Number($("setup-context").value)});
$("setup-find").onclick = () => { page("models"); $("suggest").click(); };
$("setup-machines").onclick = () => page("machines");
$("setup-project").onclick = () => page("connect");
$("setup-primary").onclick = () => action({action:"configure", node:"local", model:$("setup-model").value, role:"primary", cpu:false});
$("setup-fallback").onclick = () => action({action:"configure", node:"local", model:$("setup-model").value, role:"fallback", cpu:true});
$("check-machines").onclick = () => action({action:"health"});
$("upgrade-runtime").onclick = () => action({action:"upgrade-runtime"});
$("enable-startup").onclick = () => action({action:"autostart",enabled:true});
$("disable-startup").onclick = () => action({action:"autostart",enabled:false});
$("launch-form").onsubmit = async e => {
  e.preventDefault();
  try {
    const result = await api("/api/action", {action:"launch", project:$("launch-project").value.trim(), client:$("launch-client").value});
    notice(result.note);
  } catch (e) { notice(e.message, true); }
};
$("stop-controller").onclick = async () => {
  if (!confirm("Stop Local Control? Open managed sessions will block this action. Untracked clients may be disconnected. To keep tasks running and free GPU memory, use Gaming mode instead.")) return;
  try {
    await api("/api/stop", {acknowledge_external:true});
    authorized = false;
    $("connection").textContent = "Stopped";
    notice("Controller stopped. Start Local Control again to reconnect.");
  } catch (e) { notice(e.message, true); }
};
$("support-export").onclick = async () => {
  try {
    supportReport = await api("/api/diagnostics");
    $("support-preview").textContent = JSON.stringify(supportReport, null, 2);
    $("support-preview").hidden = false;
    $("download-support").hidden = false;
  } catch (e) { notice(e.message, true); }
};
$("download-support").onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(supportReport, null, 2)], {type:"application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = "local-control-diagnostics.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
    if (!state.primary && document.querySelector('.page.active')?.id === 'overview') page("setup");
    loadHardware();
    loadInventory();
  } catch (e) {
    if (!$("login").open) $("login").showModal();
  }
  setInterval(refresh, 2500);
})();
