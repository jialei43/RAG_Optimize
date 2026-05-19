/* ── 全局状态 ───────────────────────────────────────────────── */
const API_BASE = "/api/v1";    // 后端 API 前缀
let sessionId = null;          // 当前会话 ID
let activeSubject = null;      // 当前选择的学科代码
let isStreaming = false;        // 是否使用流式模式
let isRequesting = false;       // 是否有正在进行的请求（防止重复提交）

/* ── DOM 引用 ─────────────────────────────────────────────────── */
const messagesArea    = document.getElementById("messages-area");
const questionInput   = document.getElementById("question-input");
const sendBtn         = document.getElementById("send-btn");
const streamToggle    = document.getElementById("stream-toggle");
const clearBtn        = document.getElementById("clear-btn");
const subjectBadge    = document.getElementById("subject-badge");
const subjectList     = document.getElementById("subject-list");
const welcomePlaceholder = document.getElementById("welcome-placeholder");

/* ── 初始化 ───────────────────────────────────────────────────── */
async function init() {
  await loadSubjects();   // 加载学科列表
  await createSession();  // 创建新会话
}

/* ── 学科加载 ─────────────────────────────────────────────────── */
const SUBJECT_ICONS = {      // 每个学科对应一个 emoji 图标
  ai:      "🤖",
  java:    "☕",
  test:    "🧪",
  ops:     "⚙️",
  bigdata: "📊",
};

async function loadSubjects() {
  try {
    const resp = await fetch(`${API_BASE}/subjects`);
    const body = await resp.json();
    const subjects = body.data?.subjects || [];

    subjectList.innerHTML = "";   // 清空旧列表

    // 插入「不限学科」选项
    const allBtn = createSubjectBtn(null, "不限学科", "🔍");
    allBtn.classList.add("active");  // 默认选中
    subjectList.appendChild(allBtn);

    subjects.forEach(s => {
      subjectList.appendChild(createSubjectBtn(s.code, s.name, SUBJECT_ICONS[s.code] || "📚"));
    });
  } catch (e) {
    console.error("学科加载失败:", e);  // 失败时静默处理，不影响主流程
  }
}

function createSubjectBtn(code, name, icon) {
  const btn = document.createElement("button");
  btn.className = "subject-btn";
  btn.dataset.code = code || "";
  btn.innerHTML = `
    <span class="subject-icon">${icon}</span>
    <span>${name}</span>
  `;
  btn.addEventListener("click", () => selectSubject(code, name, btn));  // 绑定点击事件
  return btn;
}

function selectSubject(code, name, btn) {
  activeSubject = code || null;  // null 表示全学科
  document.querySelectorAll(".subject-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");   // 高亮当前选中
  subjectBadge.textContent = name;  // 更新顶部学科标识
}

/* ── 会话管理 ─────────────────────────────────────────────────── */
async function createSession() {
  try {
    const resp = await fetch(`${API_BASE}/sessions`, { method: "POST" });
    const body = await resp.json();
    sessionId = body.data?.session_id || null;  // 保存新会话 ID
    console.info("会话已创建:", sessionId);
  } catch (e) {
    console.error("会话创建失败:", e);
  }
}

async function clearHistory() {
  if (!sessionId) return;
  if (!confirm("确定清空当前对话历史？")) return;  // 二次确认防误操作

  try {
    await fetch(`${API_BASE}/sessions/${sessionId}/history`, { method: "DELETE" });
    messagesArea.innerHTML = "";          // 清空聊天区域
    welcomePlaceholder.classList.remove("hidden");  // 重新显示欢迎语
  } catch (e) {
    console.error("清空历史失败:", e);
  }
}

/* ── 消息发送主逻辑 ───────────────────────────────────────────── */
function sendMessage() {
  const question = questionInput.value.trim();
  if (!question || isRequesting) return;  // 空输入或已有请求时拒绝

  questionInput.value = "";    // 清空输入框
  autoResizeInput();           // 重置高度

  appendUserBubble(question);  // 立即显示用户消息
  hideWelcome();               // 隐藏欢迎占位

  if (isStreaming) {
    sendStreamRequest(question);  // 流式模式
  } else {
    sendInstantRequest(question); // 即时模式
  }
}

/* ── 即时问答 ─────────────────────────────────────────────────── */
async function sendInstantRequest(question) {
  setRequesting(true);
  const botRow = appendBotBubble("", true);  // 先插入 loading 气泡

  try {
    const resp = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        question:   question,
        subject:    activeSubject,
      }),
    });

    const body = await resp.json();
    if (body.code !== 0) throw new Error(body.message);  // 业务错误

    const { answer, sources } = body.data;
    updateBotBubble(botRow, answer, sources);  // 更新气泡内容
  } catch (e) {
    updateBotBubble(botRow, `请求失败: ${e.message}`, []);
  } finally {
    setRequesting(false);
  }
}

/* ── 流式问答 ─────────────────────────────────────────────────── */
async function sendStreamRequest(question) {
  setRequesting(true);
  const botRow = appendBotBubble("", false);  // 空气泡，后续追加 token
  const bubble = botRow.querySelector(".bubble");
  bubble.classList.add("typing-cursor");  // 显示打字光标

  let fullText = "";
  let sources = [];

  try {
    const resp = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        question:   question,
        subject:    activeSubject,
      }),
    });

    const reader = resp.body.getReader();        // SSE 流读取器
    const decoder = new TextDecoder("utf-8");    // UTF-8 解码器
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });  // 追加解码结果
      const lines = buffer.split("\n");
      buffer = lines.pop();   // 保留最后一个可能不完整的行

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;  // 忽略非 data 行

        const json = trimmed.slice(5).trim();  // 去掉 "data:" 前缀
        if (!json) continue;

        const event = JSON.parse(json);
        if (event.type === "token") {
          fullText += event.content;           // 追加 token
          bubble.textContent = fullText;       // 更新气泡文本
          scrollToBottom();
        } else if (event.type === "sources") {
          sources = event.sources || [];       // 接收来源列表
        } else if (event.type === "error") {
          fullText = event.message;
          bubble.textContent = fullText;
        }
      }
    }
  } catch (e) {
    bubble.textContent = `请求失败: ${e.message}`;
  } finally {
    bubble.classList.remove("typing-cursor");  // 移除打字光标
    if (sources.length > 0) appendSources(botRow, sources);  // 显示参考来源
    setRequesting(false);
  }
}

/* ── DOM 操作辅助 ─────────────────────────────────────────────── */

function appendUserBubble(text) {
  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `
    <div class="avatar user">我</div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  messagesArea.appendChild(row);
  scrollToBottom();
  return row;
}

function appendBotBubble(text, showLoading) {
  const row = document.createElement("div");
  row.className = "message-row bot";
  const content = showLoading
    ? `<span class="typing-cursor"></span>`  // 加载状态光标
    : escapeHtml(text);
  row.innerHTML = `
    <div class="avatar bot">AI</div>
    <div class="bubble-wrapper">
      <div class="bubble">${content}</div>
    </div>
  `;
  messagesArea.appendChild(row);
  scrollToBottom();
  return row;
}

function updateBotBubble(row, text, sources) {
  const bubble = row.querySelector(".bubble");
  bubble.classList.remove("typing-cursor");
  bubble.textContent = text;  // 直接赋值，自动转义安全文本
  if (sources && sources.length > 0) appendSources(row, sources);
  scrollToBottom();
}

function appendSources(row, sources) {
  const wrapper = row.querySelector(".bubble-wrapper") || row;
  const section = document.createElement("div");
  section.className = "sources-section";

  const toggle = document.createElement("div");
  toggle.className = "sources-toggle";
  toggle.innerHTML = `▸ 参考来源 (${sources.length})`;

  const list = document.createElement("div");
  list.className = "sources-list hidden";

  sources.forEach(s => {
    const chip = document.createElement("div");
    chip.className = "source-chip";
    chip.innerHTML = `
      <span class="source-label">${escapeHtml(s.subject || "")}</span>
      <span>${escapeHtml(s.excerpt || "")}</span>
    `;
    list.appendChild(chip);
  });

  toggle.addEventListener("click", () => {  // 点击展开/折叠来源列表
    const expanded = !list.classList.contains("hidden");
    list.classList.toggle("hidden", expanded);
    toggle.innerHTML = `${expanded ? "▸" : "▾"} 参考来源 (${sources.length})`;
  });

  section.appendChild(toggle);
  section.appendChild(list);
  wrapper.appendChild(section);
}

function hideWelcome() {
  if (welcomePlaceholder) welcomePlaceholder.classList.add("hidden");
}

function scrollToBottom() {
  messagesArea.scrollTop = messagesArea.scrollHeight;  // 滚动到底部
}

function setRequesting(val) {
  isRequesting = val;
  sendBtn.disabled = val;  // 请求期间禁用发送按钮
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");  // 防止 XSS 注入
}

/* ── 输入框自适应高度 ─────────────────────────────────────────── */
function autoResizeInput() {
  questionInput.style.height = "auto";
  questionInput.style.height = Math.min(questionInput.scrollHeight, 140) + "px";
}

/* ── 事件绑定 ─────────────────────────────────────────────────── */

sendBtn.addEventListener("click", sendMessage);

questionInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {  // Enter 发送，Shift+Enter 换行
    e.preventDefault();
    sendMessage();
  }
});

questionInput.addEventListener("input", autoResizeInput);  // 动态调整高度

streamToggle.addEventListener("change", e => {
  isStreaming = e.target.checked;  // 切换即时/流式模式
});

clearBtn.addEventListener("click", clearHistory);

document.getElementById("new-chat-btn").addEventListener("click", async () => {
  await createSession();   // 创建新会话
  messagesArea.innerHTML = "";
  welcomePlaceholder.classList.remove("hidden");
});

/* ── 启动 ─────────────────────────────────────────────────────── */
init();
