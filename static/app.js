/* 样本交接链路审计 — 前端逻辑（原生 JS） */

const state = {
  samples: [],
  currentId: null,
  audit: null,
  gapHours: 24,
};

const $ = (sel) => document.querySelector(sel);

// ---------- 工具 ----------

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* 非 JSON */ }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail
      : (detail?.[0]?.msg ? `输入有误：${detail[0].msg}` : `请求失败 (${res.status})`));
  }
  return data;
}

let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

// datetime-local 需要 "YYYY-MM-DDTHH:MM"
function toLocalInput(iso) {
  if (!iso) return "";
  return iso.slice(0, 16);
}

function nowLocalInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// ---------- 样本列表 ----------

async function loadSamples(selectId = null) {
  state.samples = await api("/api/samples");
  const ul = $("#sampleList");
  if (!state.samples.length) {
    ul.innerHTML = '<li class="placeholder">暂无样本<br>点击「新建」添加</li>';
  } else {
    ul.innerHTML = state.samples.map((s) => `
      <li data-id="${s.id}" class="${s.id === state.currentId ? "active" : ""}">
        <span class="s-code">${esc(s.code)}</span>
        <span class="s-name">${esc(s.name)}</span>
      </li>`).join("");
  }
  const target = selectId
    ?? (state.samples.some((s) => s.id === state.currentId) ? state.currentId : null);
  if (target) {
    state.currentId = target;
    await selectSample(target);
  } else {
    state.currentId = null;
    showEmpty();
  }
}

$("#sampleList").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-id]");
  if (li) selectSample(Number(li.dataset.id));
});

function showEmpty() {
  $("#emptyState").hidden = false;
  $("#detail").hidden = true;
}

// ---------- 审计主视图 ----------

async function selectSample(id) {
  state.currentId = id;
  document.querySelectorAll("#sampleList li[data-id]").forEach((li) => {
    li.classList.toggle("active", Number(li.dataset.id) === id);
  });
  try {
    await refreshAudit();
  } catch (err) {
    toast(err.message, true);
  }
}

async function refreshAudit() {
  if (!state.currentId) return;
  const data = await api(
    `/api/samples/${state.currentId}/audit?gap_hours=${encodeURIComponent(state.gapHours)}`
  );
  state.audit = data;
  renderDetail();
}

function renderDetail() {
  const a = state.audit;
  if (!a) return;
  $("#emptyState").hidden = true;
  $("#detail").hidden = false;

  const s = a.sample;
  $("#sampleTitle").textContent = `${s.name}（${s.code}）`;
  $("#sampleMeta").textContent =
    `创建于 ${s.created_at}${s.description ? " · " + s.description : ""}`;

  // 横幅
  const banner = $("#auditBanner");
  banner.className = `audit-banner status-${a.status}`;
  $("#auditHeadline").textContent =
    `审计结论：${a.headline}（严重 ${a.counts.error} / 警告 ${a.counts.warning} / 提示 ${a.counts.info}）`;
  $("#auditSummary").textContent = a.summary;

  const qs = `gap_hours=${encodeURIComponent(state.gapHours)}`;
  $("#btnExportMd").href = `/api/samples/${s.id}/report?fmt=markdown&${qs}`;
  $("#btnExportHtml").href = `/api/samples/${s.id}/report?fmt=html&${qs}`;

  renderFindings(a);
  renderTimeline(a);
}

const SEV_CN = { error: "严重", warning: "警告", info: "提示" };

function renderFindings(a) {
  const ul = $("#findingsList");
  if (!a.findings.length) {
    ul.innerHTML = '<li class="ok">✓ 未发现断档、重叠或逆序，交接链路完整。</li>';
    return;
  }
  ul.innerHTML = a.findings.map((f) => `
    <li>
      <span class="tag sev-${f.severity}">${SEV_CN[f.severity]} · ${esc(f.label)}</span>
      <span class="msg">${esc(f.message)}</span>
    </li>`).join("");
}

function renderTimeline(a) {
  const ol = $("#timeline");
  if (!a.timeline.length) {
    ol.innerHTML = '<li class="event-extra" style="padding-left:0">暂无交接事件，点击上方按钮录入第一条。</li>';
    return;
  }
  ol.innerHTML = a.timeline.map((e) => {
    // 该节点命中标记中的最高严重级别
    const rank = { error: 3, warning: 2, info: 1 };
    const top = e.flags.reduce((acc, f) =>
      (rank[f.severity] > (rank[acc] ?? 0) ? f.severity : acc), null) ?? "ok";
    const tags = e.flags.length
      ? e.flags.map((f) =>
          `<span class="tag sev-${f.severity}">${esc(f.label)}</span>`).join("")
      : '<span class="tag sev-ok">正常</span>';
    return `
    <li class="node sev-${top}">
      <span class="dot"></span>
      <div class="event-card">
        <div class="event-top">
          <div>
            <span class="event-time">${esc(e.occurred_at.replace("T", " "))}</span>
            <span class="entry-seq">录入序号 #${e.entry_seq}（ID ${e.id}）</span>
          </div>
          <div class="event-actions">
            <button class="btn-link" data-edit-event="${e.id}">编辑</button>
            <button class="btn-link-danger" data-del-event="${e.id}">删除</button>
          </div>
        </div>
        <div class="event-parties">
          ${esc(e.from_party)} <span class="arrow">→</span> ${esc(e.to_party)}
        </div>
        ${e.location ? `<div class="event-extra">📍 ${esc(e.location)}</div>` : ""}
        ${e.note ? `<div class="event-note">${esc(e.note)}</div>` : ""}
        <div class="event-flags">${tags}</div>
      </div>
    </li>`;
  }).join("");
}

// 时间线事件编辑/删除委托
$("#timeline").addEventListener("click", async (e) => {
  const editBtn = e.target.closest("[data-edit-event]");
  const delBtn = e.target.closest("[data-del-event]");
  if (editBtn) {
    const ev = state.audit.timeline.find((x) => x.id === Number(editBtn.dataset.editEvent));
    openEventModal(ev);
  } else if (delBtn) {
    const id = Number(delBtn.dataset.delEvent);
    if (!confirm("确定删除该交接事件吗？删除后审计结果将重新计算。")) return;
    try {
      await api(`/api/events/${id}`, { method: "DELETE" });
      toast("事件已删除");
      await refreshAudit();
    } catch (err) {
      toast(err.message, true);
    }
  }
});

// ---------- 样本弹窗 ----------

function openSampleModal(sample = null) {
  $("#sampleModalTitle").textContent = sample ? "编辑样本" : "新建样本";
  $("#sampleCode").value = sample?.code ?? "";
  $("#sampleName").value = sample?.name ?? "";
  $("#sampleDesc").value = sample?.description ?? "";
  $("#sampleModal").hidden = false;
  $("#sampleCode").focus();
}

$("#btnNewSample").addEventListener("click", () => openSampleModal());
$("#btnEditSample").addEventListener("click", () => {
  if (state.audit) openSampleModal(state.audit.sample);
});

$("#sampleForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    code: $("#sampleCode").value.trim(),
    name: $("#sampleName").value.trim(),
    description: $("#sampleDesc").value.trim() || null,
  };
  if (!payload.code || !payload.name) return toast("编号和名称不能为空", true);
  const existing = state.audit?.sample;
  try {
    if (existing && $("#sampleModalTitle").textContent === "编辑样本") {
      await api(`/api/samples/${existing.id}`, {
        method: "PUT", body: JSON.stringify(payload),
      });
      toast("样本已更新");
    } else {
      const created = await api("/api/samples", {
        method: "POST", body: JSON.stringify(payload),
      });
      state.currentId = created.id;
      toast("样本已创建");
    }
    $("#sampleModal").hidden = true;
    await loadSamples(state.currentId);
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btnDeleteSample").addEventListener("click", async () => {
  const s = state.audit?.sample;
  if (!s) return;
  if (!confirm(`确定删除样本「${s.name}」及其全部交接事件吗？此操作不可恢复。`)) return;
  try {
    await api(`/api/samples/${s.id}`, { method: "DELETE" });
    toast("样本已删除");
    state.currentId = null;
    await loadSamples();
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- 事件弹窗 ----------

function openEventModal(event = null) {
  $("#eventModalTitle").textContent = event ? "编辑交接事件" : "录入交接事件";
  $("#eventId").value = event?.id ?? "";
  $("#eventTime").value = event ? toLocalInput(event.occurred_at) : nowLocalInput();
  $("#eventFrom").value = event?.from_party ?? "";
  $("#eventTo").value = event?.to_party ?? "";
  $("#eventLocation").value = event?.location ?? "";
  $("#eventNote").value = event?.note ?? "";
  $("#eventModal").hidden = false;
  $("#eventTime").focus();
}

$("#btnNewEvent").addEventListener("click", () => openEventModal());

$("#eventForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#eventId").value;
  const payload = {
    occurred_at: $("#eventTime").value,
    from_party: $("#eventFrom").value.trim(),
    to_party: $("#eventTo").value.trim(),
    location: $("#eventLocation").value.trim() || null,
    note: $("#eventNote").value.trim() || null,
  };
  if (!payload.occurred_at || !payload.from_party || !payload.to_party) {
    return toast("时间、交出方、接收方均为必填", true);
  }
  try {
    if (id) {
      await api(`/api/events/${id}`, {
        method: "PUT", body: JSON.stringify(payload),
      });
      toast("事件已更新");
    } else {
      await api(`/api/samples/${state.currentId}/events`, {
        method: "POST", body: JSON.stringify(payload),
      });
      toast("事件已录入");
    }
    $("#eventModal").hidden = true;
    await refreshAudit();
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- 通用：关闭弹窗 / 阈值变更 ----------

document.querySelectorAll("[data-close]").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.closest(".modal-mask").hidden = true;
  });
});
document.querySelectorAll(".modal-mask").forEach((mask) => {
  mask.addEventListener("click", (e) => {
    if (e.target === mask) mask.hidden = true;
  });
});

$("#gapHours").addEventListener("change", async (e) => {
  const v = Number(e.target.value);
  if (!(v >= 0)) {
    toast("阈值需为非负数字", true);
    e.target.value = state.gapHours;
    return;
  }
  state.gapHours = v;
  if (state.currentId) {
    try { await refreshAudit(); } catch (err) { toast(err.message, true); }
  }
});

// ---------- 启动 ----------

loadSamples().catch((err) => toast(err.message, true));
