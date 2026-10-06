(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    app: $("app"),
    sidebar: $("sidebar"),
    scrim: $("scrim"),
    threadList: $("threadList"),
    search: $("searchThreads"),
    newChat: $("newChat"),
    title: $("threadTitle"),
    exportBtn: $("exportThread"),
    banner: $("banner"),
    messages: $("messages"),
    welcome: $("welcome"),
    composer: $("composer"),
    input: $("input"),
    sendBtn: $("sendBtn"),
    memoryDrawer: $("memoryDrawer"),
    memoryList: $("memoryList"),
    memoryForm: $("memoryForm"),
    memoryInput: $("memoryInput"),
    memoryCount: $("memoryCount"),
    toast: $("toast"),
  };

  const ICONS = {
    logo: '<svg viewBox="0 0 32 32"><rect width="32" height="32" rx="8"/><path d="M9 11h14M9 16h10M9 21h6"/></svg>',
    copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg>',
    retry: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4"/></svg>',
    edit: '<svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  };

  const state = {
    userId: getUserId(),
    threads: [],
    threadId: null,
    messages: [],
    controller: null,
    memories: [],
  };

  // ---------- Utilities ----------

  function getUserId() {
    const key = "threadmind:user";
    let id = null;
    try { id = localStorage.getItem(key); } catch {}
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
      try { localStorage.setItem(key, id); } catch {}
    }
    return id;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-User-Id": state.userId, ...(options.headers || {}) },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    return options.stream ? res : res.json();
  }

  function escapeHtml(text) {
    return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  let toastTimer;
  function toast(text) {
    els.toast.textContent = text;
    els.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2200);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  function flashCopied(button) {
    const original = button.innerHTML;
    button.innerHTML = button.textContent.trim() ? ICONS.check + "Copied" : ICONS.check;
    setTimeout(() => (button.innerHTML = original), 1400);
  }

  // ---------- Markdown ----------

  if (window.marked) marked.setOptions({ gfm: true, breaks: true });

  function renderMarkdown(target, text, { highlight = true } = {}) {
    if (window.marked && window.DOMPurify) {
      target.innerHTML = DOMPurify.sanitize(marked.parse(text));
    } else {
      target.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
    }
    target.querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
    target.querySelectorAll("pre > code").forEach((code) => {
      const pre = code.parentElement;
      const lang = (code.className.match(/language-([\w+#-]+)/) || [])[1] || "";
      const block = document.createElement("div");
      block.className = "code-block";
      block.innerHTML = `<div class="code-head"><span>${escapeHtml(lang || "code")}</span><button type="button">${ICONS.copy}Copy</button></div>`;
      pre.replaceWith(block);
      block.appendChild(pre);
      block.querySelector("button").addEventListener("click", (e) => {
        copyText(code.textContent);
        flashCopied(e.currentTarget);
      });
      if (highlight && window.hljs) {
        try { hljs.highlightElement(code); } catch {}
      }
    });
  }

  // ---------- Theme ----------

  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("threadmind:theme"); } catch {}
    const dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }

  $("themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("threadmind:theme", next); } catch {}
  });

  // ---------- Threads ----------

  function groupLabel(iso) {
    const date = new Date(iso);
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    const days = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return "Previous 7 days";
    if (days < 30) return "Previous 30 days";
    return "Older";
  }

  function renderThreads() {
    const query = els.search.value.trim().toLowerCase();
    const threads = state.threads.filter((t) => !query || t.title.toLowerCase().includes(query));
    els.threadList.innerHTML = "";

    if (!threads.length) {
      els.threadList.innerHTML = `<div class="thread-empty">${query ? "No chats match your search." : "No chats yet. Start one!"}</div>`;
      return;
    }

    let currentGroup = null;
    for (const thread of threads) {
      const label = groupLabel(thread.updated_at);
      if (label !== currentGroup) {
        currentGroup = label;
        const heading = document.createElement("div");
        heading.className = "thread-group";
        heading.textContent = label;
        els.threadList.appendChild(heading);
      }
      els.threadList.appendChild(threadItem(thread));
    }
  }

  function threadItem(thread) {
    const item = document.createElement("div");
    item.className = "thread-item" + (thread.id === state.threadId ? " active" : "");
    item.innerHTML = `
      <button class="thread-link" title="${escapeHtml(thread.title)}">${escapeHtml(thread.title)}</button>
      <div class="thread-actions">
        <button class="icon-btn small" data-action="rename" title="Rename" aria-label="Rename">${ICONS.edit}</button>
        <button class="icon-btn small danger" data-action="delete" title="Delete" aria-label="Delete">${ICONS.trash}</button>
      </div>`;
    item.querySelector(".thread-link").addEventListener("click", () => openThread(thread.id));
    item.querySelector('[data-action="rename"]').addEventListener("click", () => startRename(item, thread));
    item.querySelector('[data-action="delete"]').addEventListener("click", () => deleteThread(thread));
    return item;
  }

  function startRename(item, thread) {
    const input = document.createElement("input");
    input.value = thread.title;
    input.maxLength = 200;
    item.replaceChildren(input);
    input.focus();
    input.select();

    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (save && title && title !== thread.title) {
        try {
          const updated = await api(`/api/threads/${thread.id}`, { method: "PATCH", body: JSON.stringify({ title }) });
          upsertThread(updated, { keepOrder: true });
        } catch (err) {
          toast(err.message);
        }
      }
      renderThreads();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  async function deleteThread(thread) {
    if (!confirm(`Delete "${thread.title}"? This can't be undone.`)) return;
    try {
      await api(`/api/threads/${thread.id}`, { method: "DELETE" });
      state.threads = state.threads.filter((t) => t.id !== thread.id);
      if (state.threadId === thread.id) newChat();
      else renderThreads();
      toast("Chat deleted");
    } catch (err) {
      toast(err.message);
    }
  }

  function upsertThread(thread, { keepOrder = false } = {}) {
    const index = state.threads.findIndex((t) => t.id === thread.id);
    if (index >= 0 && keepOrder) {
      state.threads[index] = { ...state.threads[index], ...thread };
    } else {
      if (index >= 0) state.threads.splice(index, 1);
      state.threads.unshift(thread);
    }
    if (thread.id === state.threadId) setTitle(thread.title);
    renderThreads();
  }

  async function loadThreads() {
    try {
      state.threads = await api("/api/threads");
    } catch (err) {
      toast("Couldn't load chats: " + err.message);
    }
    renderThreads();
  }

  function setTitle(title) {
    els.title.textContent = title;
    document.title = title && title !== "New chat" ? `${title} · ThreadMind` : "ThreadMind";
  }

  function newChat() {
    stopStreaming();
    state.threadId = null;
    state.messages = [];
    setTitle("New chat");
    history.replaceState(null, "", location.pathname);
    renderMessages();
    renderThreads();
    closeSidebar();
    els.input.focus();
  }

  async function openThread(id) {
    if (id === state.threadId) return closeSidebar();
    stopStreaming();
    try {
      const thread = await api(`/api/threads/${id}`);
      state.threadId = thread.id;
      state.messages = thread.messages;
      setTitle(thread.title);
      history.replaceState(null, "", `#/t/${thread.id}`);
      renderMessages();
      renderThreads();
      closeSidebar();
      els.input.focus();
    } catch (err) {
      toast(err.message);
      if (state.threadId === null) newChat();
    }
  }

  // ---------- Messages ----------

  function renderMessages() {
    els.messages.querySelectorAll(".message").forEach((m) => m.remove());
    els.welcome.hidden = state.messages.length > 0;
    els.exportBtn.hidden = state.messages.length === 0;
    state.messages.forEach((m) => els.messages.appendChild(messageEl(m)));
    markLast();
    scrollToBottom(true);
  }

  function messageEl(message) {
    const el = document.createElement("div");
    el.className = `message ${message.role}`;
    if (message.role === "user") {
      el.innerHTML = `<div class="bubble"></div>`;
      el.querySelector(".bubble").textContent = message.content;
      return el;
    }
    el.innerHTML = `
      <div class="avatar">${ICONS.logo}</div>
      <div class="body">
        <div class="content"></div>
        <div class="msg-actions">
          <button class="icon-btn small" data-action="copy" title="Copy" aria-label="Copy">${ICONS.copy}</button>
          <button class="icon-btn small" data-action="regenerate" title="Regenerate" aria-label="Regenerate">${ICONS.retry}</button>
        </div>
      </div>`;
    renderMarkdown(el.querySelector(".content"), message.content);
    el.querySelector('[data-action="copy"]').addEventListener("click", (e) => {
      copyText(el.dataset.raw ?? message.content);
      flashCopied(e.currentTarget);
    });
    el.querySelector('[data-action="regenerate"]').addEventListener("click", regenerate);
    return el;
  }

  function markLast() {
    const all = els.messages.querySelectorAll(".message");
    all.forEach((m) => m.classList.remove("last"));
    const last = all[all.length - 1];
    if (last && last.classList.contains("assistant")) last.classList.add("last");
    // Only the latest reply can be regenerated.
    els.messages.querySelectorAll('.message.assistant [data-action="regenerate"]').forEach((b) => {
      b.hidden = !b.closest(".message").classList.contains("last");
    });
  }

  function isNearBottom() {
    const m = els.messages;
    return m.scrollHeight - m.scrollTop - m.clientHeight < 120;
  }

  function scrollToBottom(force = false) {
    if (force || isNearBottom()) els.messages.scrollTop = els.messages.scrollHeight;
  }

  // ---------- Sending & streaming ----------

  function setStreaming(on) {
    els.composer.classList.toggle("streaming", on);
    els.sendBtn.title = on ? "Stop" : "Send";
    els.sendBtn.setAttribute("aria-label", els.sendBtn.title);
    updateSendButton();
  }

  function updateSendButton() {
    els.sendBtn.disabled = !state.controller && !els.input.value.trim();
  }

  function stopStreaming() {
    if (state.controller) {
      state.controller.abort();
      state.controller = null;
      setStreaming(false);
    }
  }

  async function send(text) {
    text = text.trim();
    if (!text || state.controller) return;

    els.input.value = "";
    autosize();

    if (state.threadId === null) {
      try {
        const thread = await api("/api/threads", { method: "POST", body: JSON.stringify({}) });
        state.threadId = thread.id;
        history.replaceState(null, "", `#/t/${thread.id}`);
        upsertThread(thread);
      } catch (err) {
        els.input.value = text;
        autosize();
        return toast("Couldn't start chat: " + err.message);
      }
    }

    const userMessage = { role: "user", content: text };
    state.messages.push(userMessage);
    els.welcome.hidden = true;
    els.exportBtn.hidden = false;
    els.messages.appendChild(messageEl(userMessage));
    scrollToBottom(true);

    await streamReply(`/api/threads/${state.threadId}/messages`, { content: text });
  }

  async function regenerate() {
    if (state.controller || state.threadId === null) return;
    const lastEl = els.messages.querySelector(".message:last-of-type");
    if (state.messages.at(-1)?.role === "assistant") state.messages.pop();
    if (lastEl && lastEl.classList.contains("assistant")) lastEl.remove();
    await streamReply(`/api/threads/${state.threadId}/regenerate`);
  }

  async function streamReply(url, body) {
    const threadId = state.threadId;
    const controller = new AbortController();
    state.controller = controller;
    setStreaming(true);

    const el = messageEl({ role: "assistant", content: "" });
    const content = el.querySelector(".content");
    const actions = el.querySelector(".msg-actions");
    actions.hidden = true;
    content.innerHTML = '<div class="thinking"><span></span><span></span><span></span></div>';
    els.messages.appendChild(el);
    markLast();
    scrollToBottom(true);

    let text = "";
    let frame = null;
    let finished = false;
    const paint = () => {
      frame = null;
      renderMarkdown(content, text, { highlight: false });
      content.classList.add("cursor");
      scrollToBottom();
    };

    const fail = (message) => {
      const box = document.createElement("div");
      box.className = "error-box";
      box.innerHTML = `<span></span><button class="btn ghost danger" type="button">${ICONS.retry} Retry</button>`;
      box.querySelector("span").textContent = message;
      box.querySelector("button").addEventListener("click", regenerate);
      if (!text) content.innerHTML = "";
      el.querySelector(".body").insertBefore(box, actions);
    };

    try {
      const res = await api(url, { method: "POST", body: body ? JSON.stringify(body) : undefined, signal: controller.signal, stream: true });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          if (evt.type === "delta") {
            text += evt.text;
            if (!frame) frame = requestAnimationFrame(paint);
          } else if (evt.type === "done") {
            finished = true;
            text = evt.message.content;
            if (evt.thread) upsertThread(evt.thread);
            refreshMemoriesSoon();
          } else if (evt.type === "error") {
            finished = true;
            fail(evt.error);
          }
        }
      }
      if (!finished) fail("The connection closed before the reply finished.");
    } catch (err) {
      if (err.name !== "AbortError") fail(err.message || "Something went wrong.");
    } finally {
      if (frame) cancelAnimationFrame(frame);
      content.classList.remove("cursor");
      if (text) {
        renderMarkdown(content, text);
        el.dataset.raw = text;
        actions.hidden = false;
        if (threadId === state.threadId) state.messages.push({ role: "assistant", content: text });
      } else if (!el.querySelector(".error-box")) {
        el.remove(); // stopped before any text arrived
      }
      if (state.controller === controller) {
        state.controller = null;
        setStreaming(false);
      }
      markLast();
      scrollToBottom();
      // The thread just became the most recent one.
      const thread = state.threads.find((t) => t.id === threadId);
      if (thread) upsertThread({ ...thread, updated_at: new Date().toISOString() });
    }
  }

  // ---------- Composer ----------

  function autosize() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 220) + "px";
    updateSendButton();
  }

  els.input.addEventListener("input", autosize);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send(els.input.value);
    }
  });
  els.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.controller) stopStreaming();
    else send(els.input.value);
  });
  $("suggestions").addEventListener("click", (e) => {
    if (e.target.tagName === "BUTTON") send(e.target.textContent);
  });

  // ---------- Memory ----------

  function renderMemories() {
    els.memoryCount.textContent = state.memories.length;
    els.memoryList.innerHTML = "";
    $("clearMemory").hidden = state.memories.length === 0;
    if (!state.memories.length) {
      els.memoryList.innerHTML = '<li class="memory-empty">Nothing remembered yet. Tell ThreadMind about yourself and it will pick things up automatically.</li>';
      return;
    }
    for (const memory of state.memories) {
      const li = document.createElement("li");
      li.innerHTML = `<span></span><button class="icon-btn small danger" title="Forget" aria-label="Forget">${ICONS.close}</button>`;
      li.querySelector("span").textContent = memory.content;
      li.querySelector("button").addEventListener("click", async () => {
        try {
          await api(`/api/memories/${memory.id}`, { method: "DELETE" });
          state.memories = state.memories.filter((m) => m.id !== memory.id);
          renderMemories();
        } catch (err) {
          toast(err.message);
        }
      });
      els.memoryList.appendChild(li);
    }
  }

  async function loadMemories() {
    try {
      const before = state.memories.length;
      state.memories = await api("/api/memories");
      renderMemories();
      return state.memories.length - before;
    } catch {
      return 0;
    }
  }

  let memoryTimers = [];
  function refreshMemoriesSoon() {
    // Memory extraction runs in the background after each reply.
    memoryTimers.forEach(clearTimeout);
    memoryTimers = [2500, 7000].map((delay) =>
      setTimeout(async () => {
        const added = await loadMemories();
        if (added > 0) toast(added === 1 ? "Memory updated" : `${added} new memories saved`);
      }, delay)
    );
  }

  function openMemory() {
    loadMemories();
    els.memoryDrawer.classList.add("open");
    els.memoryDrawer.setAttribute("aria-hidden", "false");
    closeSidebar();
    setTimeout(() => els.memoryInput.focus(), 150);
  }

  function closeMemory() {
    els.memoryDrawer.classList.remove("open");
    els.memoryDrawer.setAttribute("aria-hidden", "true");
  }

  $("openMemory").addEventListener("click", openMemory);
  $("closeMemory").addEventListener("click", closeMemory);
  els.memoryDrawer.addEventListener("click", (e) => { if (e.target === els.memoryDrawer) closeMemory(); });
  els.memoryForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const content = els.memoryInput.value.trim();
    if (!content) return;
    try {
      const memory = await api("/api/memories", { method: "POST", body: JSON.stringify({ content }) });
      state.memories.push(memory);
      els.memoryInput.value = "";
      renderMemories();
    } catch (err) {
      toast(err.message);
    }
  });
  $("clearMemory").addEventListener("click", async () => {
    if (!confirm("Forget everything ThreadMind remembers about you?")) return;
    try {
      await api("/api/memories", { method: "DELETE" });
      state.memories = [];
      renderMemories();
      toast("Memory cleared");
    } catch (err) {
      toast(err.message);
    }
  });

  // ---------- Export ----------

  els.exportBtn.addEventListener("click", () => {
    const title = els.title.textContent;
    const body = state.messages
      .map((m) => `### ${m.role === "user" ? "You" : "ThreadMind"}\n\n${m.content}`)
      .join("\n\n");
    const blob = new Blob([`# ${title}\n\n${body}\n`], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (title.replace(/[^\w\- ]+/g, "").trim() || "chat") + ".md";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  // ---------- Layout & shortcuts ----------

  function closeSidebar() { els.app.classList.remove("sidebar-open"); }
  $("openSidebar").addEventListener("click", () => els.app.classList.add("sidebar-open"));
  $("closeSidebar").addEventListener("click", closeSidebar);
  els.scrim.addEventListener("click", closeSidebar);
  els.newChat.addEventListener("click", newChat);
  els.search.addEventListener("input", renderThreads);

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      newChat();
    } else if (e.key === "Escape") {
      if (els.memoryDrawer.classList.contains("open")) closeMemory();
      else if (state.controller) stopStreaming();
    }
  });

  // ---------- Startup ----------

  async function checkHealth() {
    try {
      const health = await api("/api/health");
      if (!health.llm_configured) {
        els.banner.innerHTML = "No Gemini API key configured. Add <code>GEMINI_API_KEY=...</code> to <code>backend/.env</code> and restart the server to start chatting.";
        els.banner.hidden = false;
      }
    } catch {
      els.banner.textContent = "Can't reach the ThreadMind server.";
      els.banner.hidden = false;
    }
  }

  async function init() {
    initTheme();
    autosize();
    checkHealth();
    loadMemories();
    await loadThreads();
    const match = location.hash.match(/^#\/t\/(\d+)$/);
    if (match) await openThread(Number(match[1]));
    else renderMessages();
    els.input.focus();
  }

  init();
})();
