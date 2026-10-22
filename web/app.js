/* 合同风险审查台 —— 无框架前端。
   状态只有一个 state.result；渲染函数纯函数式，便于调试。 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { result: null, fileName: "", filter: { severity: "all", category: "all" } };

  const SEV_LABEL = { high: "高", medium: "中", low: "低" };
  const REMEDY_LABEL = {
    delete: "局部删减",
    insert: "局部补入",
    "local-replace": "局部替换",
    replace: "整条重写",
    comment: "批注提示",
    "report-only": "仅入意见书",
  };

  /* ------------------------------------------------------------ 工具 */
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  let toastTimer = null;
  function toast(message, ms = 2600) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), ms);
  }

  function loading(on, text = "正在审查…") {
    $("loadingText").textContent = text;
    $("loading").hidden = !on;
  }

  function bufToB64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunk = 0x8000;
    let binary = "";
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  function b64ToBlob(b64, mime) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  /* ------------------------------------------------------------ 元信息 */
  async function loadMeta() {
    try {
      const res = await fetch("/api/meta");
      const meta = await res.json();
      const chips = [
        `<span class="chip">法条库 ${meta.statutes} 条</span>`,
        `<span class="chip">审查点 ${meta.checkpoints} 项</span>`,
        meta.llm
          ? `<span class="chip chip-on">大模型已启用 · ${esc(meta.llm_model)}</span>`
          : `<span class="chip chip-off">大模型未配置 · 规则模式</span>`,
      ];
      $("metaChips").innerHTML = chips.join("");
    } catch (err) {
      $("metaChips").innerHTML = `<span class="chip chip-off">服务未就绪</span>`;
    }
  }

  /* ------------------------------------------------------------ 请求 */
  async function requestReview(payload) {
    loading(true, "正在解析合同并逐条比对审查点…");
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `请求失败（${res.status}）`);
      state.result = data;
      state.fileName = data.filename || payload.filename || "contract";
      render();
      if (data.engine && data.engine.llm_error) {
        toast("大模型复核失败，已降级为规则结果");
      }
    } catch (err) {
      toast(err.message || "审查失败");
    } finally {
      loading(false);
    }
  }

  async function reviewFile(file) {
    if (!file) return;
    if (file.size > 12 * 1024 * 1024) {
      toast("文件超过 12 MB 上限");
      return;
    }
    const buffer = await file.arrayBuffer();
    requestReview({
      filename: file.name,
      content_b64: bufToB64(buffer),
      use_llm: $("useLlm").checked,
    });
  }

  /* ------------------------------------------------------------ 渲染 */
  function buildHighlighted(text, findings) {
    const spans = [];
    for (const finding of findings) {
      for (const ev of finding.evidence || []) {
        if (ev.end > ev.start) {
          spans.push({ s: ev.start, e: ev.end, sev: finding.severity, id: finding.id });
        }
      }
    }
    spans.sort((a, b) => a.s - b.s || b.e - a.e);

    const kept = [];
    let cursor = 0;
    for (const span of spans) {
      if (span.s >= cursor) {
        kept.push(span);
        cursor = span.e;
      }
    }

    let html = "";
    let pos = 0;
    for (const span of kept) {
      html += esc(text.slice(pos, span.s));
      html += `<mark class="hl ${span.sev}" data-cp="${esc(span.id)}">${esc(
        text.slice(span.s, span.e)
      )}</mark>`;
      pos = span.e;
    }
    html += esc(text.slice(pos));
    return html;
  }

  function renderDoc(result) {
    $("docText").innerHTML = buildHighlighted(result.contract.text, result.findings);
    $("docText").hidden = false;
    $("dropzone").hidden = true;
    $("fileName").textContent = result.filename;
    $("docActions").hidden = false;

    $("docText").querySelectorAll("mark.hl").forEach((mark) => {
      mark.addEventListener("click", () => {
        const card = document.querySelector(`.finding[data-cp="${mark.dataset.cp}"]`);
        if (card) {
          card.scrollIntoView({ behavior: "smooth", block: "center" });
          card.classList.add("flash");
          setTimeout(() => card.classList.remove("flash"), 900);
        }
      });
    });
  }

  function findingCard(finding) {
    const sev = finding.severity;
    const cites = (finding.statutes || [])
      .map(
        (s) =>
          `<span class="cite-link" data-statute="${esc(s.id)}">《民法典》${esc(s.article)}</span>`
      )
      .join("");

    let verdictTag = "";
    if (finding.llm_verdict === "dismiss") {
      verdictTag = `<span class="tag tag-dismiss" title="大模型复核后认为不构成风险">疑似误报</span>`;
    } else if (finding.llm_verdict === "uncertain") {
      verdictTag = `<span class="tag tag-uncertain" title="大模型认为信息不足">待人工确认</span>`;
    }

    const evidence = (finding.evidence || [])
      .map(
        (ev) =>
          `<div class="finding-rationale" style="color:#4a5563">「${esc(
            ev.text.length > 120 ? ev.text.slice(0, 120) + "…" : ev.text
          )}」</div>`
      )
      .join("");

    return `
      <article class="finding ${sev}" data-cp="${esc(finding.id)}">
        <div class="finding-top">
          <span class="badge ${sev}">${SEV_LABEL[sev] || sev}</span>
          <span class="finding-title">${esc(finding.name)}</span>
          ${verdictTag}
        </div>
        <div class="finding-meta">${esc(finding.category)} · ${esc(finding.id)}${
          finding.remedy
            ? ` · 建议${esc(REMEDY_LABEL[finding.remedy] || finding.remedy)}`
            : ""
        }</div>
        ${evidence}
        <p class="finding-rationale">${esc(finding.rationale)}</p>
        ${finding.llm_analysis ? `<p class="finding-rationale">结合本合同：${esc(finding.llm_analysis)}</p>` : ""}
        <div>${cites}</div>
        <p class="finding-suggest"><b>修改建议：</b>${esc(finding.suggestion)}</p>
        ${finding.revised_clause ? `<div class="revised"><b>建议条款</b><br>${esc(finding.revised_clause)}</div>` : ""}
      </article>`;
  }

  function renderResult(result) {
    const body = $("resultBody");
    const stats = result.stats;
    const levelClass = result.score >= 85 ? "pass" : result.score >= 70 ? "low" : result.score >= 50 ? "medium" : "high";

    let html = `
      <div class="score-card">
        <div class="score-top">
          <span class="score-num">${result.score}<small>/100</small></span>
          <span class="badge ${levelClass}">${esc(result.risk_level)}</span>
        </div>
        <p class="score-comment">${esc(result.overall_comment)}</p>
        <div class="stat-row">
          <span>高风险 <b>${stats.high}</b></span>
          <span>中风险 <b>${stats.medium}</b></span>
          <span>低风险 <b>${stats.low}</b></span>
          <span>共 <b>${stats.total}</b> 项</span>
          ${stats.dismissed ? `<span>疑似误报 <b>${stats.dismissed}</b></span>` : ""}
        </div>
        ${
          result.engine && result.engine.llm
            ? `<div class="engine-line">大模型复核 · ${esc(result.engine.llm_model)} ·
               ${esc(result.engine.llm_prompt)} · ${result.engine.llm_latency_ms} ms</div>`
            : result.engine && result.engine.llm_error
            ? `<div class="engine-line engine-warn">大模型复核失败，已降级为规则结果</div>`
            : ""
        }
      </div>`;

    const categories = [...new Set(result.findings.map((f) => f.category))].sort();
    html += `
      <div class="filters">
        <div class="fbtns" id="sevFilter">
          <button class="fbtn active" data-sev="all">全部 ${stats.total}</button>
          <button class="fbtn" data-sev="high">高 ${stats.high}</button>
          <button class="fbtn" data-sev="medium">中 ${stats.medium}</button>
          <button class="fbtn" data-sev="low">低 ${stats.low}</button>
        </div>
        ${
          categories.length > 1
            ? `<select class="fselect" id="catFilter">
                 <option value="all">全部类别</option>
                 ${categories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}
               </select>`
            : ""
        }
      </div>
      <div id="findingList"></div>`;

    html += `<p style="font-size:11.5px;color:#8a929c;margin-top:18px;line-height:1.7">${esc(
      result.disclaimer
    )}</p>`;

    body.innerHTML = html;
    $("btnExport").hidden = false;

    state.filter = { severity: "all", category: "all" };

    const sevBar = $("sevFilter");
    if (sevBar) {
      sevBar.addEventListener("click", (event) => {
        const btn = event.target.closest(".fbtn");
        if (!btn) return;
        state.filter.severity = btn.dataset.sev;
        sevBar.querySelectorAll(".fbtn").forEach((b) => b.classList.toggle("active", b === btn));
        renderFindingList();
      });
    }
    const catSelect = $("catFilter");
    if (catSelect) {
      catSelect.addEventListener("change", () => {
        state.filter.category = catSelect.value;
        renderFindingList();
      });
    }

    renderFindingList();
  }

  function renderFindingList() {
    const result = state.result;
    const list = $("findingList");
    if (!result || !list) return;

    const { severity, category } = state.filter;
    const visible = result.findings.filter(
      (f) =>
        (severity === "all" || f.severity === severity) &&
        (category === "all" || f.category === category)
    );

    if (!visible.length) {
      list.innerHTML = `<div class="empty"><div class="empty-icon">🔍</div>
        <p>当前筛选下没有风险点</p>
        <p class="empty-hint">换个筛选条件试试</p></div>`;
      return;
    }

    const groups = [
      ["high", "高风险"],
      ["medium", "中风险"],
      ["low", "低风险"],
    ];
    let html = "";
    for (const [key, label] of groups) {
      const items = visible.filter((f) => f.severity === key);
      if (!items.length) continue;
      html += `<div class="group-title">${label} · ${items.length}</div>`;
      html += items.map(findingCard).join("");
    }
    list.innerHTML = html;

    list.querySelectorAll("[data-statute]").forEach((el) => {
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        openStatute(el.dataset.statute);
      });
    });
  }

  function render() {
    const result = state.result;
    if (!result) return;
    renderDoc(result);
    renderResult(result);
  }

  /* ------------------------------------------------------------ 法条弹窗 */
  function openStatute(id) {
    let article = null;
    for (const finding of state.result.findings) {
      for (const s of finding.statutes || []) {
        if (s.id === id) article = s;
      }
    }
    if (!article) return;
    $("modalTitle").textContent = `《民法典》${article.article}`;
    $("modalBody").innerHTML =
      `<div class="modal-meta">${esc(article.book)}</div>${esc(article.text)}`;
    $("modal").hidden = false;
  }

  /* ------------------------------------------------------------ 导出 */
  async function exportDocx() {
    if (!state.result) return;
    const btn = $("btnExport");
    btn.disabled = true;
    btn.textContent = "生成中…";
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result: state.result }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "导出失败");
      const blob = b64ToBlob(
        data.content_b64,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = data.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast("审查意见书已导出");
    } catch (err) {
      toast(err.message || "导出失败");
    } finally {
      btn.disabled = false;
      btn.textContent = "导出意见书";
    }
  }

  /* ------------------------------------------------------------ 事件 */
  function bind() {
    $("btnPick").addEventListener("click", () => $("fileInput").click());
    $("fileInput").addEventListener("change", (event) => {
      reviewFile(event.target.files[0]);
      event.target.value = "";
    });

    const loadSample = async (key) => {
      loading(true, "正在载入样例合同…");
      try {
        const res = await fetch(`/api/sample?name=${encodeURIComponent(key)}`);
        if (!res.ok) throw new Error("样例合同不可用");
        const data = await res.json();
        await requestReview({
          filename: data.filename,
          text: data.text,
          use_llm: $("useLlm").checked,
        });
      } catch (err) {
        toast(err.message);
      } finally {
        loading(false);
      }
    };

    $("btnSample").addEventListener("click", () => loadSample("service"));
    $("btnSampleLease").addEventListener("click", () => loadSample("lease"));

    const dz = $("dropzone");
    ["dragenter", "dragover"].forEach((type) =>
      dz.addEventListener(type, (event) => {
        event.preventDefault();
        dz.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((type) =>
      dz.addEventListener(type, (event) => {
        event.preventDefault();
        dz.classList.remove("dragover");
      })
    );
    dz.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      reviewFile(file);
    });
    dz.addEventListener("click", (event) => {
      if (event.target.closest("button, label")) return;
      $("fileInput").click();
    });

    $("btnReset").addEventListener("click", () => {
      state.result = null;
      $("docText").hidden = true;
      $("docText").innerHTML = "";
      $("dropzone").hidden = false;
      $("docActions").hidden = true;
      $("btnExport").hidden = true;
      $("resultBody").innerHTML = `<div class="empty"><div class="empty-icon">🔍</div>
        <p>上传合同后，这里会列出风险条款</p>
        <p class="empty-hint">全部检测在本地完成，文件不会离开你的机器</p></div>`;
    });

    $("btnExport").addEventListener("click", exportDocx);
    $("modalClose").addEventListener("click", () => ($("modal").hidden = true));
    $("modal").addEventListener("click", (event) => {
      if (event.target.id === "modal") $("modal").hidden = true;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") $("modal").hidden = true;
    });
  }

  loadMeta();
  bind();

  // 注册 Service Worker：装到桌面后可以秒开，离线也能看到界面
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* 注册失败不影响正常使用 */
      });
    });
  }
})();
