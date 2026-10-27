"use strict";

const $ = (id) => document.getElementById(id);
const apiBase = window.APP_CONFIG.apiBaseUrl.replace(/\/+$/, "");
const number = (value) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(
        value,
      );
const state = {
  view: "chat",
  busy: false,
  dataBusy: false,
  historyBusy: false,
  conversation: null,
  preview: null,
  records: [],
  offset: 0,
  total: 0,
  limit: 15,
  editId: null,
  online: false,
};
let session;
try {
  session = localStorage.getItem("bikewise-session");
  if (!session || session.length < 32) {
    session = crypto.randomUUID();
    localStorage.setItem("bikewise-session", session);
  }
} catch {
  session = crypto.randomUUID();
  $("mode-notice").textContent =
    "브라우저 저장소가 차단되어 있습니다. 페이지를 닫으면 대화 목록에 다시 접근할 수 없습니다.";
  $("mode-notice").hidden = false;
}
$("docs-link").href = `${apiBase}/docs`;
let toastTimer;

function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 4500);
}

function errorAt(id, message = "") {
  $(id).textContent = message;
  $(id).hidden = !message;
}

async function api(path, { method = "GET", body } = {}) {
  const controller = new AbortController();
  const slow = setTimeout(() => {
    $("connection-text").textContent = "서버를 깨우고 있어요";
    $("connection-notice").textContent =
      "첫 연결은 서버 시작으로 1분 이상 걸릴 수 있습니다. 잠시 기다려 주세요.";
    $("connection-notice").hidden = false;
  }, 8000);
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(`${apiBase}${path}`, {
      method,
      signal: controller.signal,
      headers: {
        "X-Session-ID": session,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data?.detail)
        ? data.detail
            .map((item) => `${item.loc.at(-1)}: ${item.msg}`)
            .join(" / ")
        : data?.detail;
      throw new Error(
        detail || `요청에 실패했습니다 (${response.status}). 다시 시도하세요.`,
      );
    }
    state.online = true;
    $("connection").classList.remove("offline");
    $("connection-text").textContent = "서버 연결됨";
    $("connection-notice").hidden = true;
    return data;
  } catch (error) {
    if (error.name === "AbortError" || error instanceof TypeError) {
      state.online = false;
      $("connection").classList.add("offline");
      $("connection-text").textContent = "다시 연결";
      throw new Error(
        method === "GET"
          ? "서버 연결이 지연되거나 끊겼습니다. 잠시 후 상단의 다시 연결을 눌러 주세요."
          : "서버 응답을 확인하지 못했습니다. 중복 요청 전에 목록이나 대화 기록에서 저장 여부를 확인하세요.",
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    clearTimeout(slow);
  }
}

async function connect() {
  $("connection").disabled = true;
  try {
    const health = await api("/health");
    if (health.demo) {
      $("mode-notice").textContent =
        "로컬 데모 모드 · 공개 원본 731개로 시작합니다. 데이터는 로컬 파일에 저장되며, 답변은 정해진 통계 안내입니다. Firestore와 Gemini는 연결되지 않았습니다.";
      $("mode-notice").hidden = false;
    }
    await loadSummary();
    if (state.view === "data") await loadData();
    if (state.view === "history") await loadHistory();
  } catch (error) {
    errorAt("connection-notice", error.message);
  } finally {
    $("connection").disabled = false;
  }
}

const pageCopy = {
  chat: [
    "데이터에서 시작하는 대화",
    "기록 속 궁금한 점을 물어보세요. 숫자를 함께 읽어드릴게요.",
  ],
  data: [
    "매일의 기록을, 차곡차곡",
    "추가하고 수정한 데이터가 요약과 다음 대화에 반영됩니다.",
  ],
  history: [
    "지난 대화에서 이어가세요",
    "데이터를 읽으며 나눈 질문과 발견을 다시 만나보세요.",
  ],
};

async function showView() {
  const requested = location.hash.slice(1);
  state.view = Object.hasOwn(pageCopy, requested) ? requested : "chat";
  for (const view of Object.keys(pageCopy))
    $("view-" + view).hidden = state.view !== view;
  document.querySelectorAll("[data-view]").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === state.view);
    if (link.dataset.view === state.view)
      link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  [$("page-title").textContent, $("page-description").textContent] =
    pageCopy[state.view];
  if (state.view === "data") await loadData();
  if (state.view === "history") await loadHistory();
}

async function loadSummary() {
  $("refresh-summary").disabled = true;
  errorAt("summary-error");
  try {
    const summary = await api("/api/data/summary");
    renderSummary(summary);
  } catch (error) {
    errorAt("summary-error", error.message);
  } finally {
    $("summary-loading").hidden = true;
    $("refresh-summary").disabled = false;
  }
}

function renderSummary(summary) {
  $("summary-loading").hidden = true;
  $("summary-content").hidden = false;
  $("summary-period").textContent = summary.period
    ? summary.period.replace(" ~ ", "\n— ")
    : "저장된 기록이 없습니다";
  $("summary-count").textContent = `${number(summary.count)}일의 기록`;
  const metrics = summary.metrics;
  for (const name of ["total", "average", "max", "min"]) {
    $("metric-" + name).textContent =
      `${number(metrics[name])}${metrics[name] == null ? "" : " 건"}`;
  }
  $("metric-max-date").textContent = metrics.max_date || "";
  $("metric-min-date").textContent = metrics.min_date || "";
  $("summary-trend").textContent = summary.trend;
  $("trend-detail").textContent = summary.as_of
    ? `${summary.as_of} 기준 · 최근 연속 7일과 그 직전 7일의 일평균 비교. 변화율 절댓값 1% 미만은 유지입니다.`
    : "기록을 추가하면 흐름을 확인할 수 있습니다.";
}

function renderMessages(target, messages) {
  target.replaceChildren();
  for (const message of messages) {
    const article = document.createElement("article");
    article.className = `message ${message.role}`;
    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = message.role === "user" ? "나의 질문" : "Bikewise";
    const body = document.createElement("div");
    body.className = "message-body";
    body.textContent = message.content;
    article.append(label, body);
    target.append(article);
  }
}

function lockChat(locked) {
  state.busy = locked;
  $("send").disabled = locked;
  $("new-chat").disabled = locked;
  $("question").disabled = locked;
  $("chat-loading").hidden = !locked;
  $("chat-form").setAttribute("aria-busy", String(locked));
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.disabled = locked;
  });
  document
    .querySelectorAll(".history-open,.history-delete")
    .forEach((button) => {
      button.disabled = locked;
    });
  $("continue-chat").disabled = locked;
}

async function sendMessage(event) {
  event.preventDefault();
  if (state.busy) return;
  const question = $("question").value.trim();
  if (!question) return;
  const previous = state.conversation?.messages || [];
  errorAt("chat-error");
  $("welcome").hidden = true;
  renderMessages($("messages"), [
    ...previous,
    { role: "user", content: question },
  ]);
  $("question").value = "";
  $("save-status").textContent = "답변 준비 중";
  lockChat(true);
  $("chat-loading").scrollIntoView({ block: "nearest" });
  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: {
        message: question,
        ...(state.conversation
          ? { conversation_id: state.conversation.id }
          : {}),
      },
    });
    state.conversation = result.conversation;
    renderMessages($("messages"), result.conversation.messages);
    renderSummary(result.summary);
    $("save-status").textContent = "대화가 자동 저장되었습니다";
    if (state.view === "history") await loadHistory();
  } catch (error) {
    renderMessages($("messages"), previous);
    $("welcome").hidden = previous.length > 0;
    $("question").value = question;
    $("save-status").textContent = "저장 결과를 확인하세요";
    errorAt("chat-error", error.message);
  } finally {
    lockChat(false);
    $("chat-scroll").scrollTop = $("chat-scroll").scrollHeight;
    if (state.view === "chat") $("question").focus();
  }
}

function newChat() {
  if (state.busy) return;
  state.conversation = null;
  $("messages").replaceChildren();
  $("welcome").hidden = false;
  $("question").value = "";
  errorAt("chat-error");
  $("save-status").textContent = "답변 후 자동 저장";
  location.hash = "chat";
  $("question").focus();
}

function resetDataForm() {
  state.editId = null;
  $("data-form").reset();
  $("data-form-title").textContent = "새 기록 추가";
  $("save-data").textContent = "기록 추가";
  $("cancel-edit").hidden = true;
  errorAt("data-error");
}

async function loadData() {
  if (state.dataBusy) return;
  $("refresh-data").disabled = true;
  try {
    const data = await api(
      `/api/data?offset=${state.offset}&limit=${state.limit}`,
    );
    if (!data.items.length && data.total && state.offset >= data.total) {
      state.offset = Math.floor((data.total - 1) / state.limit) * state.limit;
      return await loadData();
    }
    state.records = data.items;
    state.total = data.total;
    $("data-count").textContent = `전체 ${number(data.total)}개`;
    $("data-empty").hidden = data.total !== 0;
    const body = $("data-rows");
    body.replaceChildren();
    for (const record of data.items) {
      const row = document.createElement("tr");
      for (const [text, cls] of [
        [record.date, ""],
        [number(record.value), "number-cell"],
        [record.memo || "—", "memo-cell"],
      ]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        cell.className = cls;
        if (cls === "memo-cell") cell.title = record.memo;
        row.append(cell);
      }
      const cell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";
      const edit = document.createElement("button");
      edit.textContent = "수정";
      edit.setAttribute("aria-label", record.date + " 기록 수정");
      edit.addEventListener("click", () => {
        if (state.dataBusy) return;
        state.editId = record.id;
        $("data-date").value = record.date;
        $("data-value").value = record.value;
        $("data-memo").value = record.memo;
        $("data-form-title").textContent = "기록 수정";
        $("save-data").textContent = "수정 저장";
        $("cancel-edit").hidden = false;
        errorAt("data-error");
        $("data-form").scrollIntoView({ block: "center" });
        $("data-value").focus();
      });
      const remove = document.createElement("button");
      remove.textContent = "삭제";
      remove.className = "delete";
      remove.setAttribute("aria-label", record.date + " 기록 삭제");
      remove.addEventListener("click", () => deleteData(record));
      actions.append(edit, remove);
      cell.append(actions);
      row.append(cell);
      body.append(row);
    }
    $("page-label").textContent = data.total
      ? `${state.offset + 1}–${Math.min(state.offset + state.limit, data.total)} / ${number(data.total)}`
      : "0 / 0";
    $("prev-page").disabled = state.offset === 0;
    $("next-page").disabled = state.offset + state.limit >= data.total;
  } catch (error) {
    errorAt("data-error", error.message);
  } finally {
    $("refresh-data").disabled = false;
  }
}

function lockData(locked) {
  state.dataBusy = locked;
  $("data-form").setAttribute("aria-busy", String(locked));
  $("data-form")
    .querySelectorAll("button,input")
    .forEach((element) => {
      element.disabled = locked;
    });
  document.querySelectorAll(".row-actions button").forEach((element) => {
    element.disabled = locked;
  });
  $("prev-page").disabled = locked || state.offset === 0;
  $("next-page").disabled = locked || state.offset + state.limit >= state.total;
}

async function saveData(event) {
  event.preventDefault();
  if (state.dataBusy) return;
  const editing = state.editId;
  const body = {
    date: $("data-date").value,
    value: Number($("data-value").value),
    memo: $("data-memo").value.trim(),
  };
  errorAt("data-error");
  lockData(true);
  try {
    await api(editing ? `/api/data/${editing}` : "/api/data", {
      method: editing ? "PUT" : "POST",
      body,
    });
    resetDataForm();
    state.offset = 0;
    toast(editing ? "기록을 수정했습니다." : "새 기록을 저장했습니다.");
  } catch (error) {
    errorAt("data-error", error.message);
  } finally {
    lockData(false);
  }
  await Promise.all([loadData(), loadSummary()]);
}

async function deleteData(record) {
  if (
    state.dataBusy ||
    !confirm(
      `${record.date}의 대여 기록 ${number(record.value)}건을 삭제할까요? 요약에도 반영됩니다.`,
    )
  )
    return;
  lockData(true);
  try {
    await api(`/api/data/${record.id}`, { method: "DELETE" });
    if (state.editId === record.id) resetDataForm();
    toast(`${record.date} 기록을 삭제했습니다.`);
  } catch (error) {
    errorAt("data-error", error.message);
  } finally {
    lockData(false);
  }
  await Promise.all([loadData(), loadSummary()]);
}

async function loadHistory() {
  if (state.historyBusy) return;
  state.historyBusy = true;
  $("refresh-history").disabled = true;
  errorAt("history-error");
  try {
    const items = await api("/api/conversations");
    $("history-list").replaceChildren();
    $("history-empty").hidden = items.length !== 0;
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "history-item";
      row.dataset.id = item.id;
      if (state.preview?.id === item.id) row.classList.add("selected");
      const open = document.createElement("button");
      open.className = "history-open";
      open.disabled = state.busy;
      const title = document.createElement("strong");
      title.textContent = item.title;
      const detail = document.createElement("span");
      detail.textContent = `${new Date(item.updated_at).toLocaleString("ko-KR")} · 메시지 ${item.message_count}개 · 불러오기`;
      open.append(title, detail);
      open.addEventListener("click", () => loadConversation(item.id, open));
      const remove = document.createElement("button");
      remove.className = "history-delete";
      remove.textContent = "삭제";
      remove.disabled = state.busy;
      remove.setAttribute("aria-label", `${item.title} 대화 삭제`);
      remove.addEventListener("click", async () => {
        if (state.busy || !confirm(`“${item.title}” 대화를 삭제할까요?`))
          return;
        remove.disabled = true;
        try {
          await api(`/api/conversations/${item.id}`, { method: "DELETE" });
          if (state.preview?.id === item.id) {
            state.preview = null;
            $("history-preview").hidden = true;
          }
          if (state.conversation?.id === item.id) newChat();
          toast("대화를 삭제했습니다.");
          await loadHistory();
        } catch (error) {
          errorAt("history-error", error.message);
        } finally {
          remove.disabled = state.busy;
        }
      });
      row.append(open, remove);
      $("history-list").append(row);
    }
  } catch (error) {
    errorAt("history-error", error.message);
  } finally {
    state.historyBusy = false;
    $("refresh-history").disabled = false;
  }
}

async function loadConversation(id, button) {
  if (state.busy || state.historyBusy) return;
  button.disabled = true;
  state.historyBusy = true;
  try {
    state.preview = await api(`/api/conversations/${id}`);
    $("preview-title").textContent = state.preview.title;
    renderMessages($("preview-messages"), state.preview.messages);
    $("history-preview").hidden = false;
    document
      .querySelectorAll(".history-item")
      .forEach((row) =>
        row.classList.toggle("selected", row.dataset.id === id),
      );
    $("history-preview").scrollIntoView({ block: "nearest" });
    toast("저장한 대화를 불러왔습니다.");
  } catch (error) {
    errorAt("history-error", error.message);
  } finally {
    button.disabled = false;
    state.historyBusy = false;
  }
}

$("chat-form").addEventListener("submit", sendMessage);
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("chat-form").requestSubmit();
  }
});
document.querySelectorAll("[data-question]").forEach((button) =>
  button.addEventListener("click", () => {
    $("question").value = button.dataset.question;
    $("question").focus();
  }),
);
$("new-chat").addEventListener("click", newChat);
$("connection").addEventListener("click", connect);
$("refresh-summary").addEventListener("click", loadSummary);
$("refresh-data").addEventListener("click", () =>
  Promise.all([loadData(), loadSummary()]),
);
$("refresh-history").addEventListener("click", loadHistory);
$("data-form").addEventListener("submit", saveData);
$("cancel-edit").addEventListener("click", resetDataForm);
$("prev-page").addEventListener("click", () => {
  if (!state.dataBusy) {
    state.offset = Math.max(0, state.offset - state.limit);
    loadData();
  }
});
$("next-page").addEventListener("click", () => {
  if (!state.dataBusy) {
    state.offset += state.limit;
    loadData();
  }
});
$("continue-chat").addEventListener("click", () => {
  if (state.busy || !state.preview) return;
  state.conversation = state.preview;
  renderMessages($("messages"), state.conversation.messages);
  $("welcome").hidden = true;
  $("save-status").textContent = "저장한 대화를 불러왔습니다";
  errorAt("chat-error");
  location.hash = "chat";
  $("question").focus();
});
window.addEventListener("hashchange", showView);
showView();
connect();
