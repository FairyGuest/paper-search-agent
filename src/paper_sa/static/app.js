import {icon, esc, date, heading, empty, btn, toast, modal, illustration, paperCard, safeMarkdown} from "./ui.js";

const main = document.querySelector("#main");
const state = {token:"", view:"library", papers:[], notes:[], settings:{}, jobs:[], selected:new Set(), filter:"all",
  search:null, paper:null, messages:[], note:null, dirty:false, saving:null, saveTimer:null, preview:false,
  chatSelection:null, notePending:null, excerptSaving:false, chatBusy:false, uploadTarget:"", navigation:0, jobStatuses:new Map(), polling:false,
  switching:false, sessionExpired:false};
const labels = {library:"文献工作台", graph:"文献脉络", notes:"笔记与报告", jobs:"任务中心", settings:"模型与设置", reader:"文献阅读"};
const statusLabels = {queued:"排队中",running:"进行中",waiting_user:"等待浏览器操作",completed:"已完成",failed:"失败",needs_action:"需要人工处理",cancelled:"已取消",interrupted:"已中断"};
const activeStatuses = new Set(["queued","running","waiting_user"]);
const configured = () => state.settings.has_api_key || state.settings.provider === "ollama";

async function api(path, options={}) {
  if (state.sessionExpired) throw new Error("工作目录或会话已更改，请保留未保存的草稿后刷新页面。");
  const headers = {"X-Paper-SA-Token":state.token, ...options.headers};
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch("/api" + path, {...options, headers});
  if (!response.ok) {
    if (response.status===401) {
      state.sessionExpired=true;
      document.querySelector("#workspace-stale").hidden=false;
    }
    let message = `请求失败（${response.status}）`;
    try {message = (await response.json()).detail || message;} catch {}
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return options.blob ? response.blob() : response.json();
}

async function refreshData() {
  [state.papers, state.notes] = await Promise.all([api("/papers"), api("/notes")]);
  document.querySelector("#nav-count").textContent = state.papers.length;
}

function updateProvider() {
  document.querySelector("#provider-status").textContent = configured() ? state.settings.model + " · 已配置" : "模型未配置";
}

async function navigate(view, id="") {
  await saveNote();
  const hash = "#" + view + (id ? "/" + id : "");
  if (location.hash === hash) return renderRoute();
  location.hash = hash;
}

async function renderRoute() {
  await saveNote();
  const navigation = ++state.navigation;
  const [view, id] = location.hash.replace("#","").split("/");
  state.view = labels[view] ? view : "library";
  clearChatSelection();
  main.classList.toggle("reader-view", state.view === "reader");
  state.note = null;
  state.dirty = false;
  state.preview = false;
  document.querySelector("#breadcrumb").textContent = labels[state.view];
  document.querySelectorAll(".nav-item[data-view]").forEach(item => item.classList.toggle("active", item.dataset.view === state.view));
  if (state.view !== "reader") state.paper = null;
  main.innerHTML = '<div class="loading-screen">正在加载…</div>';
  await refreshData();
  if (navigation !== state.navigation) return;
  if (state.view === "library") renderLibrary();
  if (state.view === "settings") renderSettings();
  if (state.view === "jobs") {state.jobs = await api("/jobs"); renderJobs();}
  if (state.view === "graph") await renderGraph();
  if (state.view === "notes") await renderNotes(id);
  if (state.view === "reader") await renderReader(id);
}

function visiblePapers() {
  if (state.filter === "pdf") return state.papers.filter(paper => paper.has_pdf);
  if (state.filter === "search" && state.search) return state.papers.filter(paper => state.search.papers.some(result => result.id === paper.id));
  return state.papers;
}

function renderLibrary() {
  main.innerHTML = heading("YOUR RESEARCH, IN FOCUS", "文献工作台", "把零散的论文，连接成清晰的研究脉络。",
    btn("import", "导入 PDF", "upload") + btn("focus-search", "开始新检索", "plus", "primary")) +
    `<section class="hero"><div><div class="hero-label">FOLLOW THE EVIDENCE</div><h2>好研究，始于一条<em>好线索。</em></h2><p>从研究领域、PMID 或 DOI 出发，发现、阅读并连接每一份证据。</p><div class="hero-badge">${icon("network")} PubMed 检索 &nbsp; / &nbsp; 引文拓展 &nbsp; / &nbsp; AI 辅助阅读</div></div>${illustration()}</section>
    <section class="stats">${[
      ["library",state.papers.length,"文献库 / PAPERS"],["download",state.papers.filter(paper=>paper.has_pdf).length,"本地全文 / FULL TEXT"],
      ["note",state.notes.filter(note=>note.kind==="note").length,"研究笔记 / NOTES"],["sparkle",state.notes.filter(note=>note.kind==="report").length,"综述初稿 / REPORTS"]
    ].map(([name,count,label])=>`<div class="stat"><div class="stat-icon">${icon(name)}</div><div><div class="stat-number">${String(count).padStart(2,"0")}</div><div class="stat-label">${label}</div></div></div>`).join("")}</section>
    <div class="content-grid"><div>
      <section class="panel search-panel"><div class="section-heading"><h2>${icon("search")} 发现文献</h2><span>POWERED BY PUBMED</span></div>
      <form id="search-form"><div class="search-line"><div class="search-input-wrap">${icon("search")}<input id="search-query" name="query" required maxlength="4000" placeholder="输入研究领域、关键词、PMID、DOI 或 PubMed 链接…" aria-label="文献检索内容" value="${esc(state.search?.input || "")}"></div><button class="primary" type="submit">检索文献 ${icon("arrow")}</button></div>
      <div class="search-extras"><input name="year_from" type="number" min="1800" max="2100" placeholder="起始年" aria-label="起始年份"><span>—</span><input name="year_to" type="number" min="1800" max="2100" placeholder="结束年" aria-label="结束年份"><select name="limit" aria-label="检索数量"><option value="20">20 篇</option><option value="50">50 篇</option><option value="100">100 篇</option></select>${btn("plan-query","AI 构建检索式","sparkle","text-button",'type="button"')}</div></form>
      <div class="suggestions"><span>试试这些领域</span>${["GLP-1 receptor agonist","CAR-T cell therapy","肠道菌群与免疫治疗"].map(query=>btn("example",esc(query),"","chip",`data-query="${esc(query)}"`)).join("")}</div></section>
      <div class="section-tabs"><button class="tab ${state.filter==="all"?"active":""}" data-action="filter" data-filter="all">全部文献 <span>${state.papers.length}</span></button><button class="tab ${state.filter==="pdf"?"active":""}" data-action="filter" data-filter="pdf">已有全文</button>${state.search?`<button class="tab ${state.filter==="search"?"active":""}" data-action="filter" data-filter="search">本次检索</button>`:""}${btn("history","检索历史","","text-button")}</div>
      <div id="library-results"></div>
    </div><aside class="right-rail"><section class="rail-card"><div class="rail-heading">${icon("network")} 一条线索，三个步骤</div>
      <div class="workflow-step"><div class="step-number">01</div><div><strong>从一个问题出发</strong><p>输入领域或导入种子文献，<br>找到值得深入的研究。</p></div></div>
      <div class="workflow-step"><div class="step-number">02</div><div><strong>顺着引文，发现关联</strong><p>向前追溯参考文献，<br>向后发现新的研究进展。</p></div></div>
      <div class="workflow-step"><div class="step-number">03</div><div><strong>阅读、比较、沉淀</strong><p>和论文对话，记录想法，<br>让证据汇聚为综述初稿。</p></div></div></section>
      <section class="rail-card rail-note"><div class="eyebrow">YOUR MODEL. YOUR CHOICE.</div><h3>带上你自己的研究助手</h3><p>支持 OpenAI、Claude、DeepSeek<br>及本地 Ollama 等模型。<br>自由选择，让研究更顺手。</p>${btn("settings","配置模型提供商 ↗","","text-button")}</section><p class="rail-foot">PDF 与笔记保存在你的电脑。<br>仅在使用 AI 时，将文献片段发送至<br>你配置的模型提供商。</p></aside></div>`;
  renderLibraryResults();
}

function renderLibraryResults() {
  const papers = visiblePapers();
  const selectedCount = state.selected.size;
  document.querySelector("#library-results").innerHTML =
    (state.filter==="search" && state.search ? `<div class="search-result-note">PubMed 共找到 ${state.search.total} 篇，本次保存 ${state.search.papers.length} 篇。<details><summary>查看实际检索式与提示</summary>${esc(state.search.translation)}<br>${esc(JSON.stringify(state.search.warnings || {}))}</details></div>` : "") +
    `<div class="library-toolbar"><label><input type="checkbox" id="select-all" ${papers.length && papers.every(paper=>state.selected.has(paper.id))?"checked":""}>${selectedCount ? `已选择 ${selectedCount} 篇` : "选择文献进行批量操作"}</label><div class="bulk-actions">${btn("snowball","顺藤摸瓜","network","small",selectedCount?"":"disabled") }${btn("download","下载全文","download","small",selectedCount?"":"disabled") }${btn("report","比较与综述","sparkle","small",selectedCount>=2?"":"disabled")}</div></div>
    <div class="paper-list">${papers.length ? papers.map(paper=>paperCard(paper,state.selected.has(paper.id))).join("") : empty("book",state.filter==="pdf"?"全文，还在等你发现":"你的下一条研究线索，从这里开始","检索一个感兴趣的领域，或导入本地 PDF。真实的文献与研究记录将保存在这里。",btn("focus-search","探索第一篇文献","arrow","small"))}</div>`;
}

function showSnowball(ids=[...state.selected]) {
  const papers = ids.map(id=>state.papers.find(paper=>paper.id===id));
  if (papers.some(paper=>!paper?.pmid)) return toast("请先检索 PubMed 记录；本地 PDF 没有 PMID，不能直接拓展。",true);
  state.modalSelection = ids;
  modal("顺藤摸瓜 · 文献拓展", `<p>从 ${ids.length} 篇种子文献出发，沿 PubMed 关联建立可追溯的研究脉络。引文覆盖并不完整，“没有返回”不等于“没有引用”。</p><form id="snowball-form">
    <div class="check-group"><label><input type="checkbox" name="relations" value="similar" checked>相似文献</label><label><input type="checkbox" name="relations" value="references" checked>参考文献</label><label><input type="checkbox" name="relations" value="cited_by" checked>引用它的文献</label></div>
    <div class="form-grid"><label class="field">拓展深度<select name="depth"><option value="1">1 跳 · 推荐</option><option value="2">2 跳</option><option value="3">3 跳</option></select></label><label class="field">每条路径数量<select name="per_seed"><option value="5">5 篇</option><option value="10">10 篇</option><option value="20">20 篇</option></select></label><label class="field full">最多新增文献<input type="number" name="max_papers" min="1" max="100" value="30"></label></div>
    <div class="modal-actions">${btn("close-modal","取消","","",'type="button"')}<button class="primary">开始拓展 ${icon("network")}</button></div></form>`);
}

function showReport() {
  if (!configured()) return toast("请先在模型与设置中配置 API。",true);
  const ids = [...state.selected];
  if (ids.length<2 || ids.length>20) return toast("请选择 2–20 篇文献。",true);
  const abstracts = ids.filter(id=>!state.papers.find(paper=>paper.id===id)?.has_pdf).length;
  modal("比较证据，生成综述初稿", `<p>逐篇提取证据，再对研究设计、结果与局限性进行比较；生成可继续编辑的叙述性综述初稿。</p><div class="notice">${ids.length} 篇文献中，${abstracts} 篇尚无 PDF，仅能基于摘要。预计调用模型 ${ids.length+1} 次，可能产生费用。所选文献文本将发送至 ${esc(state.settings.provider)}；请勿上传敏感患者信息。</div>
    <form id="report-form"><label class="field">综述主题 / 关注的问题<input name="topic" required maxlength="300" placeholder="例如：GLP-1 受体激动剂的心血管获益"></label><div class="modal-actions">${btn("close-modal","取消","","",'type="button"')}<button class="primary">生成综述初稿 ${icon("sparkle")}</button></div></form>`);
}

async function renderGraph() {
  const graph = await api("/graph");
  if (state.view !== "graph") return;
  const linkedIds = new Set(graph.edges.flatMap(edge=>[edge.source,edge.target]));
  const nodes = graph.nodes.filter(node=>linkedIds.has(node.id)).slice(0,70);
  const map = new Map(nodes.map((node,index)=>[node.id,{...node,x:440+330*Math.cos(index/Math.max(nodes.length,1)*2*Math.PI),y:240+180*Math.sin(index/Math.max(nodes.length,1)*2*Math.PI)}]));
  const relationNames = {similar:"相似文献",references:"参考文献",cited_by:"被引文献"};
  const colors = {similar:"#93a974",references:"#89a6b0",cited_by:"#b9a07a"};
  main.innerHTML = heading("CONNECTED EVIDENCE","文献脉络","每一条连线，都对应一条真实的 PubMed 关联。",btn("library","选择种子文献","plus","primary")) +
    (graph.edges.length ? `<section class="panel graph-panel"><div class="graph-legend"><span>相似文献</span><span>参考文献</span><span>被引文献</span></div><svg class="graph-svg" viewBox="0 0 880 480" role="img" aria-label="文献关联图">
    ${graph.edges.filter(edge=>map.has(edge.source)&&map.has(edge.target)).map(edge=>`<line x1="${map.get(edge.source).x}" y1="${map.get(edge.source).y}" x2="${map.get(edge.target).x}" y2="${map.get(edge.target).y}" stroke="${colors[edge.relation]}" opacity=".4"/>`).join("")}
    ${nodes.map(node=>`<g class="graph-node" data-action="read" data-id="${node.id}" tabindex="0" role="button" aria-label="${esc(node.metadata.title)}"><title>${esc(node.metadata.title)}</title><circle cx="${map.get(node.id).x}" cy="${map.get(node.id).y}" r="${node.has_pdf?10:7}" fill="${node.has_pdf?"#aec48f":"#e8efde"}" stroke="#8ea873"/><text x="${map.get(node.id).x}" y="${map.get(node.id).y+24}" text-anchor="middle" fill="#70865c" font-size="9">${esc(node.metadata.title.slice(0,23))}…</text></g>`).join("")}</svg><p class="subtle-label">图中最多展示 70 个关联节点；点击节点阅读。已存储 ${graph.edges.length} 条关联。</p>
    <table class="graph-table"><thead><tr><th>种子文献</th><th>关系</th><th>关联文献</th></tr></thead><tbody>${graph.edges.slice(0,300).map(edge=>{const source=graph.nodes.find(paper=>paper.id===edge.source);const target=graph.nodes.find(paper=>paper.id===edge.target);return `<tr><td>${btn("read",esc(source?.metadata.title),"","",`data-id="${edge.source}"`)}</td><td>${relationNames[edge.relation]}</td><td>${btn("read",esc(target?.metadata.title),"","",`data-id="${edge.target}"`)}</td></tr>`;}).join("")}</tbody></table></section>` :
    empty("network","一篇论文，是一张研究网络的起点","在文献工作台选择种子论文，点击“顺藤摸瓜”，这里会展示真实的相似、参考与被引关系。",btn("library","前往文献工作台","arrow","primary")));
}

async function renderReader(id) {
  const [paper,messages] = await Promise.all([api("/papers/"+id),api("/papers/"+id+"/messages")]);
  if (state.view!=="reader" || location.hash!=="#reader/"+id) return;
  state.paper=paper; state.messages=messages;
  const metadata=paper.metadata;
  main.innerHTML = `<div class="reader-heading">${btn("library",icon("back"),"","back-button")}<div><h1>${esc(metadata.title)}</h1><p>${esc(metadata.journal || "本地导入")} · ${esc(metadata.year || "年份未知")} ${paper.pmid?`· PMID ${paper.pmid}`:""}</p></div></div>
    <div class="reader-layout"><section class="pdf-pane"><div class="pane-toolbar"><span>${icon("book")} ${paper.has_pdf?`原文 PDF · ${paper.page_count} 页`:"文献摘要"}</span><div class="row-actions">${paper.has_pdf?`<a href="/api/papers/${id}/pdf?workspace_id=${state.settings.workspace_id}" target="_blank" rel="noopener" title="独立窗口打开 PDF">${icon("external")}</a>`:btn("import-paper","关联本地 PDF","upload","small")}</div></div>
    ${paper.has_pdf?`<iframe class="pdf-frame" id="pdf-frame" title="论文 PDF" src="/pdf-viewer.html?paper=${id}&amp;workspace_id=${state.settings.workspace_id}"></iframe>`:
      `<div class="abstract-view"><h2>Abstract</h2><p>${esc(metadata.abstract || "这篇记录尚无摘要。请关联 PDF，或访问出版商页面查看。")}</p><div class="notice">尚未下载全文。AI 仅能基于可用摘要回答，不能分析未提供的方法、图表与补充材料。</div>${btn("download-one","通过浏览器获取全文","download","primary",`data-id="${id}"`)} ${metadata.article_url?`<a href="${esc(metadata.article_url)}" target="_blank" rel="noopener noreferrer">PubMed ↗</a>`:""}</div>`}</section>
    <section class="reader-right" aria-label="论文对话"><div class="pane-toolbar"><span>${icon("sparkle")} 论文对话</span><span class="subtle-label">${paper.text_status==="scan"?"扫描 PDF · 未 OCR":paper.has_pdf?"附带页码来源":"仅摘要证据"}</span></div><div id="reader-content" class="chat-pane"></div></section>
    <section class="reader-notes" aria-label="阅读笔记"><div class="pane-toolbar"><span>${icon("note")} 阅读笔记</span>${btn("reader-new-note","新建笔记","plus","small")}</div><div id="reader-notes-content"></div></section></div>`;
  await renderChat();
  if (state.paper?.id!==id || state.view!=="reader") return;
  const existing = state.notes.find(note=>note.paper_id===id);
  if (existing) {
    const note = await api("/notes/"+existing.id);
    if (state.paper?.id!==id || state.view!=="reader") return;
    state.note=note;
    restoreDraft();
  }
  renderReaderNotes();
  if (!messages.length && configured() && state.settings.auto_summarize && !state.chatBusy) {
    await sendChat("",true);
  }
}

async function markdown(content,target,paper=null) {
  const result=await api("/markdown",{method:"POST",body:{content}});
  if (target?.isConnected) safeMarkdown(result.html,target,paper);
}

async function renderChat() {
  const container=document.querySelector("#reader-content");
  if (!container || state.view!=="reader") return;
  clearChatSelection();
  container.className="chat-pane";
  container.innerHTML=`<div class="chat-messages" id="chat-messages">${state.messages.length?state.messages.map((message,index)=>`<div class="message ${message.role}"><div class="message-header">${message.role==="assistant"?icon("sparkle")+" Paper SA":"你"}</div><div class="message-content markdown" data-message="${index}"></div>${message.role==="assistant"?`<div class="message-actions">${btn("save-answer","整段存入笔记","note","",`data-index="${index}"`)}<span class="scope-label">${esc(message.scope)}</span></div>`:""}</div>`).join(""):
    `<div class="chat-welcome"><div class="small-orbit">✳</div><h3>让阅读，成为一场对话。</h3><p>从研究问题到方法局限，<br>基于当前论文的证据，一起读得更深入。</p><div class="suggested-questions">${btn("summarize","按医学论文结构总结","sparkle")}${["这项研究的 PICO 是什么？","主要结果与临床意义是什么？","研究有哪些偏倚和局限性？"].map(question=>btn("question",question,"arrow","",`data-question="${question}"`)).join("")}</div></div>`}
    ${state.chatBusy?'<div class="typing"><i></i><i></i><i></i> 正在阅读证据并生成回答…</div>':""}</div>
    <div class="chat-input-area"><div class="selection-hint">选中回答中的文字，即可添加到右侧笔记。</div><form id="chat-form"><textarea id="chat-question" placeholder="针对当前论文提出问题…" maxlength="8000" aria-label="向论文提问"></textarea><div class="chat-send-row"><span>Ctrl / ⌘ + Enter 发送</span><button class="primary" ${state.chatBusy?"disabled":""}>发送 ${icon("send")}</button></div></form><div class="chat-disclaimer">AI 可能出错，请核对原文 · 文献片段将发送至你配置的模型</div></div>`;
  await Promise.all(state.messages.map(async(message,index)=>{
    const target=container.querySelector(`[data-message="${index}"]`);
    if (message.role==="user") target.textContent=message.content;
    else await markdown(message.content,target,state.paper);
  }));
  const messages=document.querySelector("#chat-messages");
  if (messages) messages.scrollTop=messages.scrollHeight;
}

async function sendChat(question,summarize=false) {
  if (!state.paper || state.chatBusy) return;
  if (!configured()) return toast("先配置模型提供商与 API Key，就可以开始对话。",true);
  const paperId=state.paper.id;
  state.chatBusy=true;
  await renderChat();
  try {
    await api(`/papers/${paperId}/chat`,{method:"POST",body:{question,summarize}});
    const messages=await api(`/papers/${paperId}/messages`);
    if (state.paper?.id===paperId) state.messages=messages;
  } catch(error) {toast(error.message,true);}
  finally {state.chatBusy=false;if (state.paper?.id===paperId) await renderChat();}
}

async function ensurePaperNote() {
  if (state.note?.paper_id===state.paper.id) return state.note;
  const paperId=state.paper.id;
  const existing=state.notes.find(note=>note.paper_id===paperId);
  if (!existing) return createReaderNote();
  const note=await api("/notes/"+existing.id);
  if (state.paper?.id!==paperId || state.view!=="reader") throw new Error("页面已切换，请回到原论文后再添加摘录。");
  state.note=note;
  restoreDraft();
  return note;
}

async function createReaderNote() {
  if (state.notePending) return state.notePending;
  const paper=state.paper;
  if (!paper || state.view!=="reader") return;
  state.notePending=(async()=>{
    await saveNote();
    if (state.paper?.id!==paper.id || state.view!=="reader") return;
    const number=state.notes.filter(note=>note.paper_id===paper.id).length+1;
    const note=await api("/notes",{method:"POST",body:{
      title:(paper.metadata.title+" · 阅读笔记 "+number).slice(0,500),
      paper_id:paper.id,
      content:"# 阅读笔记\n\n## 研究问题\n\n## 方法与结果\n\n## 我的思考\n\n## 待核对事项\n",
    }});
    state.notes.unshift(note);
    if (state.paper?.id!==paper.id || state.view!=="reader") return note;
    state.note=note;
    state.dirty=false;
    state.preview=false;
    renderReaderNotes();
    return note;
  })();
  document.querySelectorAll('[data-action="reader-new-note"]').forEach(button=>button.disabled=true);
  try {return await state.notePending;}
  finally {
    state.notePending=null;
    document.querySelectorAll('[data-action="reader-new-note"]').forEach(button=>button.disabled=false);
  }
}

function renderReaderNotes() {
  const container=document.querySelector("#reader-notes-content");
  if (!container || !state.paper) return;
  if (!state.note || state.note.paper_id!==state.paper.id) {
    container.innerHTML=empty("note","边读边记，让思考留在原文旁","点击右上角“新建笔记”开始记录。选中对话文字后添加摘录，也会自动创建这篇论文的笔记。");
    return;
  }
  const notes=state.notes.filter(note=>note.paper_id===state.paper.id);
  container.innerHTML=`<div class="reader-note-picker"><label for="reader-note-select">当前笔记</label><select id="reader-note-select" aria-label="选择当前论文笔记">${notes.map(note=>`<option value="${note.id}" ${note.id===state.note.id?"selected":""}>${esc(note.id===state.note.id?state.note.title:note.title)}</option>`).join("")}</select></div>${editorMarkup()}`;
  if (state.preview) markdown(state.note.content,document.querySelector("#note-preview"),state.paper).catch(error=>toast(error.message,true));
}

async function switchReaderNote(noteId) {
  const paperId=state.paper?.id;
  if (!state.notes.some(note=>note.id===noteId && note.paper_id===paperId)) return;
  try {
    await saveNote();
    const note=await api("/notes/"+noteId);
    if (state.paper?.id!==paperId || state.view!=="reader") return;
    state.note=note;
    state.preview=false;
    restoreDraft();
    renderReaderNotes();
  } catch(error) {
    const picker=document.querySelector("#reader-note-select");
    if (picker && state.note) picker.value=state.note.id;
    throw error;
  }
}

function clearChatSelection() {
  state.chatSelection=null;
  const toolbar=document.querySelector("#chat-selection-toolbar");
  if (toolbar) toolbar.hidden=true;
}

function captureChatSelection() {
  if (state.excerptSaving) return;
  const selection=window.getSelection();
  if (state.view!=="reader" || !state.paper || !selection?.rangeCount || selection.isCollapsed) return clearChatSelection();
  const range=selection.getRangeAt(0);
  const start=range.startContainer.nodeType===Node.ELEMENT_NODE?range.startContainer:range.startContainer.parentElement;
  const end=range.endContainer.nodeType===Node.ELEMENT_NODE?range.endContainer:range.endContainer.parentElement;
  const content=start?.closest(".message.assistant .message-content");
  if (!content || end?.closest(".message.assistant .message-content")!==content || !content.contains(range.commonAncestorContainer)) return clearChatSelection();
  const text=selection.toString().trim();
  if (!text) return clearChatSelection();
  const message=state.messages[Number(content.dataset.message)];
  if (!message || message.role!=="assistant") return clearChatSelection();
  state.chatSelection={paperId:state.paper.id,message,text,range:range.cloneRange(),content};
  positionChatSelection();
}

function positionChatSelection() {
  const selected=state.chatSelection;
  const toolbar=document.querySelector("#chat-selection-toolbar");
  const chat=document.querySelector("#chat-messages");
  if (!selected || !toolbar || !chat || !selected.content.isConnected) return clearChatSelection();
  const bounds=selected.range.getBoundingClientRect();
  const visible=chat.getBoundingClientRect();
  if (bounds.bottom<=visible.top || bounds.top>=visible.bottom || bounds.bottom<0 || bounds.top>innerHeight) {
    toolbar.hidden=true;
    return;
  }
  toolbar.hidden=false;
  const width=toolbar.offsetWidth;
  const height=toolbar.offsetHeight;
  toolbar.style.left=Math.max(8,Math.min(innerWidth-width-8,bounds.left+(bounds.width-width)/2))+"px";
  const below=Math.min(bounds.bottom,visible.bottom)+8;
  toolbar.style.top=(below+height<innerHeight-8?below:Math.max(8,Math.min(bounds.top,visible.bottom)-height-8))+"px";
}

function rememberNoteDraft() {
  try {localStorage.setItem(draftKey(state.note.id),JSON.stringify({title:state.note.title,content:state.note.content}));} catch {}
}

function draftKey(noteId) {
  return "paper-sa-draft-"+state.settings.workspace_id+"-"+noteId;
}

async function appendChatExcerpt(message,text,selectedOnly,paperId) {
  if (state.excerptSaving) return;
  state.excerptSaving=true;
  const button=document.querySelector('[data-action="save-selection"]');
  button.disabled=true;
  try {
    await saveNote();
    if (state.paper?.id!==paperId || state.view!=="reader") throw new Error("页面已切换，请回到原论文后再添加摘录。");
    const note=await ensurePaperNote();
    if (state.paper?.id!==paperId || state.note?.id!==note?.id || state.view!=="reader") throw new Error("页面已切换，未将摘录写入其他论文。");
    const metadata=state.paper.metadata;
    const citations=[...new Set(message.content.match(/\[P\d+(?:\s*[·:]\s*(?:p\.\d+|摘要))?\]/g)||[])];
    const body=selectedOnly?text.split("\n").map(line=>"> "+line).join("\n"):text;
    const source=[metadata.title,state.paper.pmid?"PMID "+state.paper.pmid:"",metadata.doi?"DOI "+metadata.doi:""].filter(Boolean).join(" · ");
    const excerpt="\n\n## "+(selectedOnly?"对话选文摘录":"AI 阅读摘录")+"\n\n"+body+
      "\n\n**来源**："+source+"\n\n**证据范围**："+(message.scope||"请核对原文")+
      (selectedOnly && citations.length?"\n\n**该条回答的来源线索**："+citations.join(" "):"")+
      "\n\n*AI 对话摘录，引用原文请与论文核对。*\n";
    if (note.content.length+excerpt.length>500000) throw new Error("笔记内容已接近上限，请新建笔记后再添加。");
    note.content+=excerpt;
    state.dirty=true;
    rememberNoteDraft();
    const editor=document.querySelector("#note-editor");
    if (editor) {editor.value=note.content;editor.scrollTop=editor.scrollHeight;}
    else renderReaderNotes();
    await saveNote();
    if (state.paper?.id===paperId && state.view==="reader") {
      clearChatSelection();
      toast(selectedOnly?"选中文字已添加到当前阅读笔记。":"已保存到这篇论文的阅读笔记。");
    }
  } finally {state.excerptSaving=false;button.disabled=false;}
}

function restoreDraft() {
  try {
    let draft=JSON.parse(localStorage.getItem(draftKey(state.note.id)));
    if (!draft) {
      const legacyKey="paper-sa-draft-"+state.note.id;
      const legacy=JSON.parse(localStorage.getItem(legacyKey));
      if (legacy && confirm("发现旧版未保存草稿，但旧版没有记录所属工作目录。请核对当前笔记；是否将该草稿恢复到当前目录？")) {
        localStorage.setItem(draftKey(state.note.id),JSON.stringify(legacy));
        localStorage.removeItem(legacyKey);
        draft=legacy;
      }
    }
    if (draft && draft.content!==state.note.content) {
      state.note.content=draft.content;state.note.title=draft.title;state.dirty=true;
      toast("已恢复此浏览器中未保存的笔记草稿。");
    }
  } catch {}
}

function editorMarkup() {
  const note=state.note;
  return `<div class="editor-shell"><div class="editor-toolbar">${btn("note-bold","B","","small") }${btn("note-heading","H₂","","small") }${btn("preview",state.preview?"仅编辑":"预览","","small")}<span id="save-state" class="save-state">${state.dirty?"未保存":"已保存到本地"}</span><select id="export-format" aria-label="导出格式"><option value="md">Markdown</option><option value="pdf">PDF</option><option value="docx">Word (.docx)</option></select>${btn("export","导出","download","small")}</div>
    <input class="note-title" id="note-title" aria-label="笔记标题" maxlength="500" value="${esc(note.title)}"><div class="editor-body ${state.preview?"preview-mode":""}"><textarea class="note-editor" id="note-editor" aria-label="Markdown 笔记编辑器" maxlength="500000" spellcheck="false">${esc(note.content)}</textarea>${state.preview?'<article class="note-preview markdown" id="note-preview"></article>':""}</div></div>`;
}

async function renderNotes(id) {
  const selected=state.notes.find(note=>note.id===id) || state.notes[0];
  if (selected) {state.note=await api("/notes/"+selected.id);restoreDraft();}
  main.innerHTML=heading("THINKING, PRESERVED","笔记与报告","让阅读中的思考，成为下一步研究的起点。",btn("new-note","新建笔记","plus","primary"))+
    `<div class="notes-layout"><div class="note-list">${state.notes.map(note=>`<button class="note-list-item ${state.note?.id===note.id?"active":""}" data-action="open-note" data-id="${note.id}"><div class="note-kind">${note.kind==="report"?"◈ 综述初稿":"▤ 研究笔记"}</div>${esc(note.title)}<small>${date(note.updated_at)}</small></button>`).join("")}</div>
    ${state.note?editorMarkup():empty("note","给想法一个留下来的地方","阅读笔记、证据比较与综述初稿，都会出现在这里。支持 Markdown 编辑以及 PDF、Word 导出。",btn("new-note","写下第一条笔记","plus","primary"))}</div>`;
}

function noteChanged() {
  if (!state.note) return;
  state.note.title=document.querySelector("#note-title")?.value || "未命名笔记";
  state.note.content=document.querySelector("#note-editor")?.value ?? state.note.content;
  state.dirty=true;
  rememberNoteDraft();
  const label=document.querySelector("#save-state");if(label)label.textContent="正在输入…";
  clearTimeout(state.saveTimer);
  state.saveTimer=setTimeout(()=>saveNote().catch(error=>toast(error.message,true)),850);
}

async function saveNote() {
  clearTimeout(state.saveTimer);
  if (state.saving) await state.saving;
  if (!state.note || !state.dirty) return;
  const note=state.note;
  const snapshot={title:note.title,content:note.content,revision:note.revision};
  const label=document.querySelector("#save-state");if(label)label.textContent="保存中…";
  state.saving=api("/notes/"+note.id,{method:"PUT",body:snapshot});
  try {
    const result=await state.saving;
    note.revision=result.revision;
    state.notes=state.notes.map(existing=>existing.id===result.id?result:existing);
    const option=document.querySelector(`#reader-note-select option[value="${result.id}"]`);
    if (option) option.textContent=result.title;
    if (state.note?.id===note.id && note.content===snapshot.content && note.title===snapshot.title) {
      state.dirty=false;
      try {localStorage.removeItem(draftKey(note.id));} catch {}
    }
    if(label?.isConnected)label.textContent=state.dirty?"有新修改":"已保存到本地";
    if (state.preview && document.querySelector("#note-preview")) await markdown(note.content,document.querySelector("#note-preview"),state.paper);
  } catch(error) {
    if(label?.isConnected)label.textContent="保存失败 · 草稿已保留";
    throw error;
  } finally {state.saving=null;}
  if(state.dirty) await saveNote();
}

async function exportNote() {
  await saveNote();
  const format=document.querySelector("#export-format").value;
  const blob=await api(`/notes/${state.note.id}/export?format=${format}`,{blob:true});
  downloadBlob(blob,state.note.title+"."+format);
}

function downloadBlob(blob,name) {
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");anchor.href=url;anchor.download=name;anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}

function renderSettings() {
  const settings=state.settings;
  main.innerHTML=heading("BUILT AROUND YOU","模型与设置","你的模型、你的浏览器、你的研究数据。")+
    `<form id="settings-form"><section class="panel settings-section"><h2>模型提供商</h2><div class="form-grid">
    <label class="field">提供商<select id="provider" name="provider">${Object.keys(settings.providers).map(provider=>`<option value="${provider}" ${provider===settings.provider?"selected":""}>${{openai:"OpenAI",anthropic:"Anthropic / Claude",deepseek:"DeepSeek",gemini:"Google Gemini",ollama:"Ollama · 本地模型",custom:"自定义 · OpenAI 兼容"}[provider]}</option>`).join("")}</select></label>
    <label class="field">模型名称<input name="model" id="model" required value="${esc(settings.model)}"><small>可填写提供商支持的任意模型 ID，预设仅作为示例。</small></label>
    <label class="field full">API Base URL<input name="base_url" id="base-url" type="url" required value="${esc(settings.base_url)}"><small>填写 API 根地址（通常以 /v1 结尾），不包含 /chat/completions。仅 Anthropic 使用 Messages 协议。</small></label>
    <label class="field full">API Key<input name="api_key" id="api-key" type="password" autocomplete="new-password" placeholder="${settings.has_api_key?"已保存 · 留空保留当前密钥":"输入你的 API Key（Ollama 可留空）"}"><small>密钥加密保存在本地；不回显到页面。切换提供商或 Base URL 后需重新输入密钥。</small></label>
    <label class="field checkbox full"><input name="clear_api_key" type="checkbox">删除已保存的模型 API Key</label>
    <label class="field checkbox full"><input name="auto_summarize" type="checkbox" ${settings.auto_summarize?"checked":""}>打开未对话的论文时，自动发送片段并生成结构化总结</label>
    <label class="field">每篇论文上下文字符上限<input type="number" name="context_chars" min="8000" max="100000" step="1000" value="${settings.context_chars}"><small>这是字符限制而非 token；较小上下文可降低模型费用。</small></label></div>
    <div class="notice info">使用对话、检索式建议或综述功能时，相关文本会发送到上述提供商。不要上传含患者身份信息或其他敏感数据的文件。选择本地 Ollama 可在本机进行模型推理。</div>
    <div class="settings-actions"><button class="primary">保存设置 ${icon("check")}</button>${btn("test-provider","测试已保存的连接","","",'type="button"')}</div></section>
    <section class="panel settings-section"><h2>文献来源与下载</h2><div class="form-grid">
    <label class="field">联系邮箱<input name="contact_email" type="email" value="${esc(settings.contact_email)}" placeholder="research@university.edu"><small>用于 NCBI 请求标识与 Unpaywall 合法开放获取地址查询；不填则跳过 Unpaywall。</small></label>
    <label class="field">NCBI API Key（可选）<input name="ncbi_api_key" type="password" autocomplete="new-password" placeholder="${settings.has_ncbi_api_key?"已保存 · 留空保留":"提高 PubMed 请求速率"}"></label>
    <label class="field checkbox full"><input name="clear_ncbi_api_key" type="checkbox">删除已保存的 NCBI API Key</label>
    <label class="field">浏览器下载模式<select name="browser_mode"><option value="managed" ${settings.browser_mode==="managed"?"selected":""}>专用可见浏览器（推荐）</option><option value="cdp" ${settings.browser_mode==="cdp"?"selected":""}>连接本机 Chrome（CDP）</option><option value="manual" ${settings.browser_mode==="manual"?"selected":""}>系统浏览器 · 手动下载并导入</option></select></label>
    <label class="field">Chrome CDP 地址<input name="cdp_url" value="${esc(settings.cdp_url)}"></label></div>
    <div class="notice">专用浏览器不会自动继承你日常 Chrome 的登录态，请在首次打开后手动登录机构；后续会保留此专用配置的 cookies。CDP 仅连接本机已开启调试的 Chrome。遇登录墙或验证码需本人操作，不会绕过订阅授权。</div>
    <div class="settings-actions"><button class="primary">保存设置</button>${btn("open-browser","打开浏览器并登录","external","",'type="button"')}</div></section></form>
    <section class="panel settings-section" id="workspace-settings"><h2>工作目录</h2><p class="muted">当前使用的目录</p><p class="workspace-path" id="current-workspace"><code>${esc(settings.data_dir)}</code></p>
    <p class="subtle-label">每个目录独立保存论文 PDF、笔记、对话、模型设置与浏览器登录态。切换不移动、复制或删除原目录的数据。</p>
    <div class="settings-actions">${btn("switch-workspace","切换工作目录","external","primary",'type="button"')}</div>
    <p class="subtle-label workspace-hint">切换后立即生效，并记为下次运行 paper-sa 的默认目录；命令行 --data-dir 或 PAPER_SA_HOME 仍优先。备份前请退出程序，不要公开共享数据目录。</p></section>`;
}

async function showWorkspaceDialog() {
  await saveNote();
  modal("切换工作目录", `<p>当前目录：<span class="workspace-path">${esc(state.settings.data_dir)}</span></p>
    <form id="workspace-form"><label class="field">新建或打开目录<input id="workspace-path" name="path" required maxlength="4096" autocomplete="off" list="workspace-recent" placeholder="填写完整路径，例如 D:\\Research\\项目A">
    <small>支持空目录、尚未创建的目录，或已有的 Paper SA 工作目录。也可从下方建议中选择最近目录。</small></label>
    <datalist id="workspace-recent">${(state.settings.workspace?.recent||[]).map(path=>`<option value="${esc(path)}"></option>`).join("")}</datalist>
    <div class="notice">不会搬迁旧数据。新目录有独立的模型设置，可能需要重新填写 API Key。切换会关闭专用下载浏览器，并使其他标签页的旧会话失效；请先保存本页设置及其他页面的笔记。</div>
    <div class="modal-actions">${btn("close-modal","取消","","",'type="button"')}<button type="submit" class="primary">确认切换</button></div></form>`);
  document.querySelector("#workspace-path").focus();
}

async function switchWorkspace(path) {
  await saveNote();
  state.switching=true;
  try {
    await api("/workspace/switch",{method:"POST",body:{path}});
    try {sessionStorage.setItem("paper-sa-workspace-switched","1");} catch {}
    history.replaceState(null,"","#library");
    location.reload();
  } catch(error) {
    state.switching=false;
    throw error;
  }
}

function renderJobs() {
  main.innerHTML=heading("RESEARCH IN MOTION","任务中心","检索拓展、全文下载与报告生成，进展都在这里。",btn("refresh-jobs","刷新","activity"))+
    `<div class="job-list">${state.jobs.length?state.jobs.map(job=>`<article class="panel job-card"><div class="job-header"><strong>${icon({download:"download",snowball:"network",report:"sparkle"}[job.kind])} ${{download:"全文下载",snowball:"顺藤摸瓜",report:"综述初稿"}[job.kind]}</strong><span class="badge ${job.status}">${statusLabels[job.status]||job.status}</span></div><p class="job-message">${esc(job.message)}</p><div class="job-progress"><span style="width:${job.progress}%"></span></div>
    ${job.result?.papers?.length?`<details class="job-details"><summary>查看逐篇结果（${job.result.papers.length}）</summary><ul>${job.result.papers.map(result=>`<li>${esc(state.papers.find(paper=>paper.id===result.paper_id)?.metadata.title || result.paper_id)}<br>${esc(result.route || result.message || result.status)}</li>`).join("")}</ul></details>`:""}
    <div class="job-footer"><span>${date(job.created_at)} · ${job.progress}%</span><div class="row-actions">${job.result?.note_id?btn("open-note","打开报告","note","small",`data-id="${job.result.note_id}"`):""}${job.result?.paper_ids?.length?btn("library","查看文献","library","small"):""}${activeStatuses.has(job.status)?btn("cancel-job","取消","","small",`data-id="${job.id}"`):""}</div></div></article>`).join(""):empty("activity","让研究继续向前","发起文献拓展、下载全文或生成综述后，你可以在这里查看进度、人工处理提示与逐篇结果。")}</div>`;
}

async function pollJobs() {
  if(state.polling || state.sessionExpired) return;
  if(state.switching){setTimeout(pollJobs,2000);return;}
  state.polling=true;
  try {
    const jobs=await api("/jobs");
    let completed=false;
    for(const job of jobs) {
      const previous=state.jobStatuses.get(job.id);
      if(previous && activeStatuses.has(previous) && !activeStatuses.has(job.status)) {
        completed=true;toast(job.message,["failed","needs_action","interrupted"].includes(job.status));
      }
      state.jobStatuses.set(job.id,job.status);
    }
    state.jobs=jobs;
    document.querySelector("#job-count").hidden=!jobs.some(job=>activeStatuses.has(job.status));
    if(completed) await refreshData();
    if(state.view==="jobs") renderJobs();
  } catch {} finally {
    state.polling=false;
    setTimeout(pollJobs,state.jobs.some(job=>activeStatuses.has(job.status))?2000:8000);
  }
}

async function startJob(path,body) {
  const job=await api(path,{method:"POST",body});
  state.jobStatuses.set(job.id,job.status);
  document.querySelector("#modal").close();
  toast("任务已启动，可以在任务中心查看进度。");
  await navigate("jobs");
}

async function importPDF(file) {
  if(!file) return;
  if(file.size>60*1024*1024) return toast("PDF 不能超过 60 MB。",true);
  const body=new FormData();body.append("file",file);body.append("paper_id",state.uploadTarget || "");
  toast("正在导入 PDF 并提取文本…");
  const paper=await api("/papers/upload",{method:"POST",body});
  state.uploadTarget="";
  await refreshData();
  toast(paper.text_status==="scan"?"PDF 已导入，但未检测到足够文本（扫描件需要先 OCR）。":"PDF 已保存并完成文本提取。");
  await navigate("reader",paper.id);
}

document.addEventListener("click",async event=>{
  const element=event.target.closest("[data-action],[data-view]");
  if(!element || element.disabled || state.switching) return;
  if(element.dataset.view) {event.preventDefault();try{await navigate(element.dataset.view);}catch(error){toast(error.message,true);}return;}
  const action=element.dataset.action;
  try {
    if(["library","settings"].includes(action)) return await navigate(action);
    if(action==="close-modal") return document.querySelector("#modal").close();
    if(action==="switch-workspace") return await showWorkspaceDialog();
    if(action==="focus-search"){document.querySelector("#search-query")?.focus();return;}
    if(action==="example"){document.querySelector("#search-query").value=element.dataset.query;document.querySelector("#search-query").focus();return;}
    if(action==="filter"){state.filter=element.dataset.filter;renderLibrary();return;}
    if(action==="read") return await navigate("reader",element.dataset.id);
    if(action==="import" || action==="import-paper"){state.uploadTarget=action==="import-paper"?state.paper.id:"";document.querySelector("#pdf-upload").click();return;}
    if(action==="snowball") return showSnowball();
    if(action==="snowball-one") return showSnowball([element.dataset.id]);
    if(action==="report") return showReport();
    if(action==="download" || action==="download-one") return await startJob("/downloads",{paper_ids:action==="download-one"?[element.dataset.id]:[...state.selected]});
    if(action==="refresh-jobs"){state.jobs=await api("/jobs");renderJobs();return;}
    if(action==="cancel-job"){await api("/jobs/"+element.dataset.id+"/cancel",{method:"POST"});toast("已请求取消；正在进行的网络请求完成后停止。");return;}
    if(action==="open-note") return await navigate("notes",element.dataset.id);
    if(action==="new-note"){await saveNote();const note=await api("/notes",{method:"POST",body:{title:"新的研究笔记",content:"# 研究笔记\n\n"}});return await navigate("notes",note.id);}
    if(action==="summarize") return await sendChat("",true);
    if(action==="question") return await sendChat(element.dataset.question);
    if(action==="pdf-page"){document.querySelector("#pdf-frame").src=`/pdf-viewer.html?paper=${state.paper.id}&workspace_id=${state.settings.workspace_id}#page=${element.dataset.page}`;return;}
    if(action==="reader-new-note") return await createReaderNote();
    if(action==="save-selection"){
      const selected=state.chatSelection;
      if (!selected || !selected.content.isConnected) return toast("请先选中一条 AI 回答中的文字。",true);
      return await appendChatExcerpt(selected.message,selected.text,true,selected.paperId);
    }
    if(action==="save-answer"){
      const message=state.messages[Number(element.dataset.index)];
      if (message?.role==="assistant") await appendChatExcerpt(message,message.content,false,state.paper.id);
      return;
    }
    if(action==="preview"){
      await saveNote();state.preview=!state.preview;document.querySelector(".editor-shell").outerHTML=editorMarkup();
      if(state.preview) await markdown(state.note.content,document.querySelector("#note-preview"),state.paper);return;
    }
    if(action==="note-bold" || action==="note-heading"){
      const editor=document.querySelector("#note-editor");const start=editor.selectionStart,end=editor.selectionEnd;
      const text=editor.value.slice(start,end);editor.setRangeText(action==="note-bold"?"**"+(text||"重点")+"**":"\n## "+(text||"小节")+"\n",start,end,"end");editor.focus();noteChanged();return;
    }
    if(action==="export") return await exportNote();
    if(action==="test-provider"){
      element.disabled=true;toast("正在测试已保存的模型配置（一次简短 API 调用）…");
      try{const result=await api("/settings/test",{method:"POST"});toast(result.message);}finally{element.disabled=false;}return;
    }
    if(action==="open-browser"){
      element.disabled=true;try{const result=await api("/browser/open",{method:"POST"});toast(result.message);}finally{element.disabled=false;}return;
    }
    if(action==="plan-query"){
      if(!configured())return toast("先配置模型；英文关键词或 PMID 检索不需要 API Key。",true);
      const query=document.querySelector("#search-query").value.trim();if(!query)return toast("请先输入研究领域。",true);
      element.disabled=true;
      try{const result=await api("/search/plan",{method:"POST",body:{query}});const input=document.querySelector("#search-query");if(input)input.value=result.query;toast("检索式已生成，请检查后点击“检索文献”。");}finally{element.disabled=false;}return;
    }
    if(action==="history"){
      const history=await api("/search/history");
      modal("检索历史",history.length?`<div class="job-list">${history.map(item=>`<div class="job-card panel"><p class="job-message">${esc(item.query)}</p><small class="muted">${date(item.created_at)}</small><details class="job-details"><summary>检索参数</summary>${esc(item.details)}</details></div>`).join("")}</div>`:"<p>尚无检索记录。</p>");return;
    }
    if(action==="show-guide") modal("从线索到研究报告",'<p>1. 输入关键词、PMID、DOI 或领域（中文主题建议先用 AI 构建英文检索式）。<br><br>2. 选择种子论文，沿参考文献、被引文献与相似文献拓展。<br><br>3. 下载合法可访问的 PDF；首次请在专用浏览器中手动登录机构。<br><br>4. 左侧读原文，右侧对话与记录笔记。<br><br>5. 选择 2–20 篇论文生成比较与综述初稿，核验后导出。</p><div class="notice info">检索、阅读本地 PDF 与手写笔记不需要模型 API Key。AI 功能可能产生提供商费用。</div>');
  }catch(error){toast(error.message,true);}
});

document.addEventListener("submit",async event=>{
  event.preventDefault();
  if(state.switching) return;
  const form=event.target, data=new FormData(form), button=form.querySelector('button[type=submit],button:not([type])');
  if(button)button.disabled=true;
  try {
    if(form.id==="workspace-form") return await switchWorkspace(String(data.get("path")).trim());
    if(form.id==="search-form"){
      const body={query:data.get("query"),limit:Number(data.get("limit")),year_from:data.get("year_from")?Number(data.get("year_from")):null,year_to:data.get("year_to")?Number(data.get("year_to")):null};
      const result=await api("/search",{method:"POST",body});
      state.search={...result,input:body.query};state.filter="search";await refreshData();
      if(state.view==="library")renderLibrary();toast(`已保存 ${result.papers.length} 篇 PubMed 文献。`);
    }
    if(form.id==="snowball-form"){
      const relations=data.getAll("relations");if(!relations.length)throw new Error("至少选择一种关联关系");
      await startJob("/snowball",{paper_ids:state.modalSelection,relations,depth:Number(data.get("depth")),per_seed:Number(data.get("per_seed")),max_papers:Number(data.get("max_papers"))});
    }
    if(form.id==="report-form")await startJob("/reports",{paper_ids:[...state.selected],topic:data.get("topic")});
    if(form.id==="chat-form"){const question=document.querySelector("#chat-question").value.trim();if(question)await sendChat(question);}
    if(form.id==="settings-form"){
      const body=Object.fromEntries(data);
      for(const field of ["auto_summarize","clear_api_key","clear_ncbi_api_key"])body[field]=data.has(field);
      body.context_chars=Number(body.context_chars);
      state.settings=await api("/settings",{method:"PUT",body});updateProvider();renderSettings();toast("设置已加密保存到本地。");
    }
  }catch(error){toast(error.message,true);}finally{if(button?.isConnected)button.disabled=false;}
});

document.addEventListener("change",event=>{
  const element=event.target;
  if(element.dataset.select){element.checked?state.selected.add(element.dataset.select):state.selected.delete(element.dataset.select);renderLibraryResults();}
  if(element.id==="select-all"){visiblePapers().forEach(paper=>element.checked?state.selected.add(paper.id):state.selected.delete(paper.id));renderLibraryResults();}
  if(element.id==="provider"){
    const preset=state.settings.providers[element.value];document.querySelector("#model").value=preset.model;
    document.querySelector("#base-url").value=preset.base_url;document.querySelector("#api-key").value="";document.querySelector("#api-key").placeholder="切换提供商后，请输入对应 API Key";
  }
  if(element.id==="pdf-upload"){importPDF(element.files[0]).catch(error=>toast(error.message,true));element.value="";}
  if(element.id==="reader-note-select")switchReaderNote(element.value).catch(error=>toast(error.message,true));
});
document.addEventListener("selectionchange",captureChatSelection);
document.addEventListener("pointerup",()=>requestAnimationFrame(captureChatSelection));
document.addEventListener("pointerdown",event=>{
  if(event.target.closest('[data-action="save-selection"]'))event.preventDefault();
});
document.addEventListener("scroll",positionChatSelection,true);
window.addEventListener("resize",positionChatSelection);
document.addEventListener("input",event=>{if(["note-editor","note-title"].includes(event.target.id))noteChanged();});
document.addEventListener("keydown",event=>{
  if((event.ctrlKey||event.metaKey)&&event.key==="Enter" && event.target.id==="chat-question"){event.preventDefault();document.querySelector("#chat-form").requestSubmit();}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s" && state.note){event.preventDefault();saveNote().then(()=>toast("笔记已保存。")).catch(error=>toast(error.message,true));}
  if(event.key==="Enter" && event.target.matches(".graph-node"))event.target.dispatchEvent(new MouseEvent("click",{bubbles:true}));
});
window.addEventListener("beforeunload",event=>{if(state.dirty||state.saving){event.preventDefault();event.returnValue="";}});
window.addEventListener("hashchange",()=>renderRoute().catch(error=>toast(error.message,true)));
document.addEventListener("dragover",event=>{if(event.dataTransfer?.types.includes("Files")){event.preventDefault();main.classList.add("drag-active");}});
document.addEventListener("dragleave",event=>{if(!event.relatedTarget)main.classList.remove("drag-active");});
document.addEventListener("drop",event=>{
  if(!event.dataTransfer?.files.length)return;
  event.preventDefault();main.classList.remove("drag-active");state.uploadTarget=state.paper&&!state.paper.has_pdf?state.paper.id:"";
  importPDF(event.dataTransfer.files[0]).catch(error=>toast(error.message,true));
});

async function init() {
  document.querySelectorAll("[data-icon]").forEach(element=>element.innerHTML=icon(element.dataset.icon));
  const bootstrap=await fetch("/api/bootstrap").then(response=>response.json());state.token=bootstrap.token;
  state.settings=await api("/settings");updateProvider();await renderRoute();pollJobs();
  try {
    if(sessionStorage.getItem("paper-sa-workspace-switched")) {
      sessionStorage.removeItem("paper-sa-workspace-switched");
      toast("工作目录已切换，原目录的数据保持不变。");
    }
  } catch {}
}
init().catch(error=>{main.innerHTML=empty("activity","工作空间暂时无法连接",error.message,btn("library","重试","arrow"));toast(error.message,true);});
