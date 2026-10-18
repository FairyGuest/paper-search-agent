import {getDocument, GlobalWorkerOptions} from "/vendor/pdfjs/legacy/build/pdf.mjs";

GlobalWorkerOptions.workerSrc = "/vendor/pdfjs/legacy/build/pdf.worker.mjs";
const paperId = new URLSearchParams(location.search).get("paper");
const workspaceId = new URLSearchParams(location.search).get("workspace_id");
const canvas = document.querySelector("#pdf-canvas");
const status = document.querySelector("#pdf-status");
const pageInput = document.querySelector("#page-number");
const container = document.querySelector("#pdf-container");
let pdf = null;
let currentPage = 1;
let zoom = null;
let lastScale = 1;
let activeRender = null;
let generation = 0;
let resizeTimer;

function requestedPage() {
  const requested = Number(new URLSearchParams(location.hash.slice(1)).get("page")) || 1;
  return Math.max(1, Math.min(pdf?.numPages || 1, requested));
}

async function render() {
  if (!pdf) return;
  canvas.dataset.ready = "false";
  const request = ++generation;
  if (activeRender) {
    activeRender.cancel();
    try {await activeRender.promise;} catch {}
    activeRender = null;
  }
  const page = await pdf.getPage(currentPage);
  if (request !== generation) return;
  const unit = page.getViewport({scale: 1});
  const scale = zoom ?? Math.max(0.2, (container.clientWidth - 36) / unit.width);
  lastScale = scale;
  const viewport = page.getViewport({scale});
  const density = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.floor(viewport.width * density);
  canvas.height = Math.floor(viewport.height * density);
  canvas.style.width = viewport.width + "px";
  canvas.style.height = viewport.height + "px";
  canvas.hidden = false;
  status.hidden = true;
  canvas.dataset.ready = "false";
  activeRender = page.render({canvasContext: canvas.getContext("2d"), viewport,
    transform: density === 1 ? null : [density, 0, 0, density, 0, 0]});
  try {
    await activeRender.promise;
    if (request !== generation) return;
    canvas.dataset.ready = "true";
    pageInput.value = currentPage;
    document.querySelector("#page-count").textContent = pdf.numPages;
    document.querySelector("#previous").disabled = currentPage === 1;
    document.querySelector("#next").disabled = currentPage === pdf.numPages;
    canvas.setAttribute("aria-label", "PDF 第 " + currentPage + " 页，共 " + pdf.numPages + " 页");
  } catch(error) {
    if (error.name !== "RenderingCancelledException") showError();
  }
}

function showError() {
  status.hidden = false;
  status.textContent = "PDF 暂时无法显示。请刷新页面；也可点击阅读区右上角，在独立窗口打开原始 PDF。";
}

function go(page) {
  currentPage = Math.max(1, Math.min(pdf.numPages, Number(page) || 1));
  const hash = "#page=" + currentPage;
  if (location.hash === hash) render().catch(showError);
  else location.hash = hash;
}

document.querySelector("#previous").onclick = () => pdf && go(currentPage - 1);
document.querySelector("#next").onclick = () => pdf && go(currentPage + 1);
pageInput.onchange = () => pdf && go(pageInput.value);
document.querySelector("#fit").onclick = () => {zoom = null;render().catch(showError);};
document.querySelector("#zoom-in").onclick = () => {zoom = Math.min(3, lastScale + 0.25);render().catch(showError);};
document.querySelector("#zoom-out").onclick = () => {zoom = Math.max(0.25, lastScale - 0.25);render().catch(showError);};
window.addEventListener("hashchange", () => {currentPage = requestedPage();render().catch(showError);});
window.addEventListener("resize", () => {clearTimeout(resizeTimer);resizeTimer = setTimeout(() => render().catch(showError), 150);});

async function load() {
  if (!/^[a-f0-9]{32}$/.test(paperId || "")) throw new Error("Invalid paper ID");
  const scope = workspaceId ? "?workspace_id=" + encodeURIComponent(workspaceId) : "";
  pdf = await getDocument({url: "/api/papers/" + paperId + "/pdf" + scope, withCredentials: true,
    cMapUrl: "/vendor/pdfjs/cmaps/", cMapPacked: true, standardFontDataUrl: "/vendor/pdfjs/standard_fonts/",
    wasmUrl: "/vendor/pdfjs/wasm/", isEvalSupported: false}).promise;
  pageInput.max = pdf.numPages;
  currentPage = requestedPage();
  await render();
}
load().catch(showError);
