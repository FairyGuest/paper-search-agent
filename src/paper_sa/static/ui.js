const paths = {
  library: '<path d="M4 4h5v16H4zM10 4h5v16h-5zM17 4l4 15-4 1-4-15"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  network: '<circle cx="12" cy="5" r="3"/><circle cx="5" cy="18" r="3"/><circle cx="19" cy="18" r="3"/><path d="m10.5 8-4 7m7-7 4 7M8 18h8"/>',
  note: '<path d="M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h6"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 4 2 2v4l4 2 3-1 3 1 4-2v-4l2-2-2-4-3-1-1-3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 15v6h16v-6"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  back: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  sparkle: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
  book: '<path d="M12 5v16M3 4c5-1 7 0 9 2 2-2 4-3 9-2v15c-5-1-7 0-9 2-2-2-4-3-9-2z"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 4H4v16h16v-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  send: '<path d="m3 3 18 9-18 9 4-9zM7 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>'
};

export const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.note}</svg>`;
export const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]);
export const date = value => value ? new Date(value).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "";
export const heading = (eyebrow, title, subtitle, actions="") => `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="actions">${actions}</div></div>`;
export const empty = (name, title, text, action="") => `<div class="empty-state"><div class="empty-emblem">${icon(name)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
export const btn = (action, label, name="", classes="", attrs="") => `<button class="${classes}" data-action="${action}" ${attrs}>${name ? icon(name) : ""}${label}</button>`;

export function toast(message, error=false) {
  const element = document.createElement("div");
  element.className = "toast" + (error ? " error" : "");
  element.textContent = message;
  const region = document.querySelector("#toast-region");
  while (region.children.length >= 2) region.firstElementChild.remove();
  region.append(element);
  setTimeout(() => element.remove(), error ? 9000 : 5000);
}

export function modal(title, content) {
  document.querySelector("#modal-content").innerHTML = `<div class="modal-inner"><div class="modal-heading"><h2>${esc(title)}</h2>${btn("close-modal", icon("close"))}</div>${content}</div>`;
  document.querySelector("#modal").showModal();
}

export function illustration() {
  return `<svg class="hero-illustration" viewBox="0 0 310 165" fill="none" aria-hidden="true">
    <circle cx="174" cy="83" r="73" stroke="#d1ddbe" stroke-dasharray="3 5"/>
    <circle cx="174" cy="83" r="54" stroke="#dce5d0"/>
    <path d="m54 119 69-59 51 23 62-53m-62 53 70 54" stroke="#a9bc8c" stroke-dasharray="3 4"/>
    <circle cx="54" cy="119" r="10" fill="#dce8cb" stroke="#baca9e"/><circle cx="54" cy="119" r="3" fill="#9ab27b"/>
    <circle cx="241" cy="31" r="7" fill="#d7e5c4" stroke="#adc18c"/>
    <circle cx="246" cy="140" r="11" fill="#dce8cb" stroke="#baca9e"/><path d="m242 140 3 3 5-6" stroke="#8ca569"/>
    <g transform="rotate(-12 147 85)"><rect x="105" y="26" width="78" height="108" rx="6" fill="#e8efdd" stroke="#c0cea8"/><rect x="113" y="33" width="76" height="108" rx="6" fill="#f8fbf2" stroke="#bdcda4"/><path d="M129 49h30m-30 8h44m-44 8h39" stroke="#c8d5b4" stroke-width="3"/><rect x="129" y="79" width="13" height="23" rx="2" fill="#d0debb"/><rect x="147" y="70" width="13" height="32" rx="2" fill="#b4c99a"/><rect x="165" y="87" width="10" height="15" rx="2" fill="#dde7ce"/><path d="M129 116h43m-43 7h32" stroke="#d4dec4" stroke-width="2"/></g>
    <g transform="rotate(10 220 105)"><rect x="186" y="65" width="64" height="78" rx="5" fill="#fff" stroke="#cbd7b8"/><rect x="198" y="77" width="20" height="5" rx="2" fill="#b6c997"/><path d="M198 91h38m-38 7h32m-32 7h36m-36 14h38m-38 7h23" stroke="#d6e0c9" stroke-width="2"/></g>
    <path d="m76 37 2-5 2 5 5 2-5 2-2 5-2-5-5-2zm201 46 1.5-4 1.5 4 4 1.5-4 1.5-1.5 4-1.5-4-4-1.5z" fill="#b5c69d"/>
  </svg>`;
}

export function paperCard(paper, selected) {
  const metadata = paper.metadata;
  const tags = (metadata.publication_types || []).slice(0,2);
  return `<article class="paper-card ${selected ? "selected" : ""}">
    <input type="checkbox" data-select="${paper.id}" aria-label="选择 ${esc(metadata.title)}" ${selected ? "checked" : ""}>
    <div><div class="paper-meta"><span class="journal">${esc(metadata.journal || "本地导入")}</span><span>·</span><span>${esc(metadata.year || "年份未标注")}</span>${paper.pmid ? `<span>PMID ${paper.pmid}</span>` : ""}</div>
    <button class="paper-title" data-action="read" data-id="${paper.id}">${esc(metadata.title)}</button>
    <div class="paper-authors">${esc((metadata.authors || []).slice(0,3).join(", ") || "作者信息未提供")}${(metadata.authors || []).length > 3 ? " et al." : ""}</div>
    <div class="paper-bottom"><div class="paper-tags">${paper.has_pdf ? '<span class="pdf-tag">PDF 已就绪</span>' : '<span>摘要可读</span>'}${tags.map(tag => `<span>${esc(tag)}</span>`).join("")}</div>
    <div class="paper-actions">${btn("read", paper.has_pdf ? "阅读全文" : "阅读摘要", "book", "", `data-id="${paper.id}"`)}${btn("snowball-one", "拓展", "network", "", `data-id="${paper.id}"`)}</div></div></div></article>`;
}

export function safeMarkdown(html, target, paper=null) {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  parsed.querySelectorAll("script,style,iframe,object,embed,img,form,input,button").forEach(node => node.remove());
  parsed.querySelectorAll("*").forEach(node => {
    [...node.attributes].forEach(attribute => {
      if (attribute.name.startsWith("on") || ["style","srcdoc","id"].includes(attribute.name)) node.removeAttribute(attribute.name);
    });
  });
  parsed.querySelectorAll("a").forEach(link => {
    if (!/^https?:\/\//i.test(link.getAttribute("href") || "")) link.removeAttribute("href");
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });
  parsed.querySelectorAll("blockquote").forEach(quote => {
    if (quote.querySelector("strong")?.textContent.trim() === "论文原文") quote.classList.add("paper-original");
  });
  if (paper?.has_pdf) {
    const walker = parsed.createTreeWalker(parsed.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const pattern = /\[P1\s*[·:]\s*p\.(\d+)\]/g;
      const matches = [...node.textContent.matchAll(pattern)];
      if (!matches.length) continue;
      const fragment = document.createDocumentFragment();
      let offset = 0;
      for (const match of matches) {
        fragment.append(node.textContent.slice(offset, match.index));
        const page = Number(match[1]);
        if (page > 0 && page <= paper.page_count) {
          const button = document.createElement("button");
          button.className = "citation";
          button.dataset.action = "pdf-page";
          button.dataset.page = page;
          button.textContent = match[0];
          fragment.append(button);
        } else fragment.append(match[0]);
        offset = match.index + match[0].length;
      }
      fragment.append(node.textContent.slice(offset));
      node.replaceWith(fragment);
    }
  }
  target.replaceChildren(...parsed.body.childNodes);
}
