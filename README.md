# Paper SA

本地优先的医学文献研究工作台，以 browser-paper-download skill 的浏览器授权下载流程为基础，提供 PubMed 检索、引文拓展、PDF 阅读、文献问答、Markdown 笔记与叙述性综述初稿。

## 快速开始

Windows：下载本项目后，双击 **install.cmd**（需要网络；不需要预装 Python 或 Node.js）。

macOS / Linux：在项目目录运行 **bash install.sh**。

安装后在新终端运行 **paper-sa**，浏览器会打开 http://127.0.0.1:8765 。

开发安装：使用 Python 3.11+ 和 uv，运行 **uv sync --extra dev**，然后 **uv run paper-sa**。

## 已实现

- 中文前端：文献工作台、关系图、PDF 阅读与对话、笔记与报告、任务中心、模型设置。
- 领域/关键词、PMID、DOI、PMCID 和 PubMed 链接检索；可由 AI 建议英文检索式，确认后执行。
- 参考、被引、相似关系的 1–3 跳文献拓展，去重、来源追踪、后台进度与取消。
- PMC/出版商/Unpaywall 下载路由，可见浏览器、机构登录态、PDF 校验与本地归档；失败明确提示人工操作。
- PDF、论文对话、Markdown 笔记三栏阅读；支持新建/切换论文笔记、选中回答文字一键入笔记，以及“论文原文”引用与页码跳转。
- 2–20 篇论文的逐篇证据提取、比较综合与叙述性综述初稿；报告可继续编辑。
- 笔记自动保存、冲突检测和 Markdown / PDF / Word 导出。
- 自定义模型与 Base URL、加密保存密钥，支持 OpenAI 兼容、Anthropic、Ollama 等协议。
- 设置页切换独立工作目录，记住最近目录与下次默认目录；原目录数据保留，运行中的任务和旧标签页受到保护。

## 验证

    uv run pytest -q
    uv run python tests/browser_smoke.py
    uv run ruff check src tests scripts
    uv build

浏览器测试需要本机 Chrome，使用临时数据与明确标记的模拟文献/模型，不调用真实付费模型。覆盖检索、设置、问答、笔记自动保存、三种导出、PDF 实际渲染、关系拓展、报告生成、移动布局及浏览器下载事件。

首次使用请先配置模型并在专用浏览器中自行登录机构。不会继承日常 Chrome cookies，不绕过验证码或付费墙。扫描 PDF 不自动 OCR；模型与机构访问需要用户自己的配置。报告是待人工核验的叙述性综述初稿，不是系统综述或医学建议。

安装与使用详见 [docs/SETUP.md](docs/SETUP.md)，架构与隐私边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，上游来源见 [THIRD_PARTY.md](THIRD_PARTY.md)。
