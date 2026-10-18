# 安装与使用

## 一键安装

下载或复制完整项目文件夹，必须包含 pyproject.toml、uv.lock、src。

- Windows 10/11：双击 install.cmd。安装完成后以前台进程启动，关闭服务按 Ctrl+C。
- PowerShell：执行 ./install.ps1；可选 -SkipBrowser（不下载 Chromium）、-NoPath（不修改用户 PATH）、-Launch（安装后启动）。
- macOS / Linux：执行 bash install.sh。可选 --skip-browser。

脚本从 Astral 官方 HTTPS 地址获取 uv，然后安装独立的 Python 3.12 与隔离工具环境，不修改系统 Python，不需要 Node.js、Git、Office 或 LaTeX。依赖由 uv.lock 导出约束。首次安装需要访问 Astral、GitHub、PyPI 与 Playwright CDN；企业代理、防火墙或网络限制可能导致失败。请预留约 1 GB 磁盘空间。

Linux 图形化浏览器依赖发行版共享库与桌面环境；脚本不会静默执行 sudo。若浏览器提示缺失库，可由管理员安装 Chrome，或在开发环境执行 uv run playwright install-deps chromium。无桌面环境时使用手动下载与导入。macOS/Linux 脚本需要在对应操作系统上另行验收。

重新运行安装脚本可更新工具环境，不会删除用户数据。卸载可执行 uv tool uninstall paper-sa；数据目录保留。

## 启动与开发

    paper-sa
    paper-sa --port 8899
    paper-sa --no-browser
    paper-sa --data-dir "D:\Research\PaperSA"
    paper-sa install-browser
    paper-sa --version

默认仅监听 127.0.0.1:8765，不支持对公网开放。若命令未找到，请打开新终端或使用安装器打印的完整路径。同一数据目录同时只应启动一个实例。

    uv sync --extra dev --frozen
    uv run paper-sa --no-browser
    uv run pytest
    uv run ruff check src tests
    uv build

前端是随 Python wheel 分发的静态 ES Modules，无需前端构建；所有资源本地加载。

## 切换工作目录

进入左下角“模型与设置” → “工作目录” → “切换工作目录”，输入完整路径（如 D:\Research\项目A），或选择最近使用过的路径，再点击“确认切换”。

- 支持创建尚不存在的目录、使用空目录，或打开已有的 Paper SA 工作目录。不会把任意非空文件夹当作工作目录，也不允许选择磁盘根目录、当前工作目录的父目录或子目录。
- 切换立即生效并回到文献工作台，不需要手动重启服务。各目录的论文、笔记、对话、模型设置与浏览器登录态相互独立；新目录需要单独配置模型。此功能是打开/新建工作区，不是数据迁移，不移动、复制或删除旧文件。
- 检索、问答、保存、下载和报告任务尚未结束时会拒绝切换；请等待结束或取消后重试。被其他 Paper SA 实例占用的目录不能打开。
- 切换前请保存模型设置和其他标签页的笔记。切换会关闭专用下载浏览器（不关闭用户的 CDP Chrome），其他标签页的旧会话失效，需保留草稿后刷新。笔记草稿按工作目录隔离，避免复制数据库后相同笔记 ID 混写；旧版未归属目录的草稿恢复前需要人工确认。
- 最近 8 个目录和默认目录记录在系统用户配置目录的 workspaces.json 中（Windows 通常为 %LOCALAPPDATA%\paper-sa）。启动优先级是：命令行 --data-dir → 环境变量 PAPER_SA_HOME → 最近确认的工作目录 → 原默认数据目录。普通 paper-sa 启动会记住上次选择；始终带 --data-dir 的启动脚本仍会使用指定目录。

切回旧目录即可重新看到原有内容。备份或迁移仍请先退出程序，再备份完整数据目录，不能只复制 PDF 或 settings.json；加密设置还需要原 .secret.key。

## 模型配置

支持 OpenAI、DeepSeek、Gemini 的 OpenAI 兼容端点、自定义 Chat Completions、Anthropic Messages，以及 Ollama /v1 API。填写提供商、模型 ID、Base URL 与 API Key，保存后测试连接。预设模型只是示例，实际可用性取决于提供商与账户。

切换提供商或 Base URL 会清除旧模型密钥，避免发送给其他服务。切换时需填写新密钥；同一端点保存时留空保留原密钥。Ollama 无需密钥，但需自行安装 Ollama 并下载模型，例如 qwen3:8b；安装器不自动下载大型语言模型。

PubMed 检索、PDF 阅读与手动笔记无需模型密钥。中文领域建议先点击“AI 构建检索式”，检查英文检索式后再检索。

自动总结在首次打开没有对话记录的论文时发送文本给模型；可以关闭，改用自定义问题或手动总结。输出必须核对原文。

## 三栏阅读与摘录

打开论文后，桌面端同时展示左侧 PDF、中间对话和右侧笔记。小屏幕会按顺序排列，避免三栏过窄。

- 点击笔记栏“新建笔记”，直接为当前论文创建笔记，不离开 PDF 或对话。同一论文支持多份笔记，通过“当前笔记”下拉框切换，切换前自动保存。
- 在 AI 回答内拖选需要的文字，点击浮动按钮“添加选中文字到笔记”，只追加所选文字，不覆盖原有内容；没有笔记时会自动新建。
- 点击回答下方“整段存入笔记”可保留完整 Markdown 回答。摘录附论文来源、证据范围和回答中的页码线索，便于回到原文核对。
- 手写笔记、AI 对话互不替换；笔记仍支持自动保存、预览与三种格式导出。

精读对话要求模型按以下格式提供支持性原句，并另写中文解读：

> **论文原文** [P1 · p.3]
>
> 此处为从已提供片段中逐字摘录的原语言句子（这里只是格式示例）。

**解读**：解释原句与问题的关系。只有摘要时应使用“[P1 · 摘要]”并标明摘要来源。不能把翻译、改写或推断当作原文；无法找到原句时须说明。该规则约束模型输出，但不替代人工引文核验；已有历史回答不会被自动改写。

## 浏览器授权下载

沿用原 skill 原则：元数据解析 → 合法 PDF 路由 → 真实可见浏览器 → 校验 PDF → 本地归档。

1. 推荐专用可见浏览器：优先系统 Chrome，若不可用则使用安装器提供的 Chromium。
2. 设置中点击“打开浏览器并登录”，自行进入学校或机构登录页。专用配置不会继承日常 Chrome 的 cookies，第一次需要人工登录，后续保留登录态。
3. Chrome 应设置为下载 PDF。专用配置自动启用此项；CDP 模式需自行到 chrome://settings/content/pdfDocuments 设置。
4. 选择论文后点击“下载全文”。优先尝试 Unpaywall 合法 OA 地址，然后使用 PMC / 出版商浏览器路径。
5. 登录或验证码由本人在浏览器中处理。失败会明确显示“需要人工处理”，不会生成假 PDF。登录后可重试，也可以将自行下载的 PDF 拖入对应论文阅读页关联。

CDP 模式连接已由用户开启本机调试端口的 Chrome。Chrome 136+ 通常要求使用独立 --user-data-dir，不能直接调试默认用户目录。不要将调试端口暴露给网络。退出 Paper SA 不会关闭用户的 CDP Chrome。

系统浏览器模式只打开候选页面，需要下载后手动导入；不会扫描或移动整个 Downloads 文件夹，以免误归档。

程序不输入账号密码、不购买、不绕过付费墙、不访问影子图书馆，不承诺所有论文均可下载。请遵守出版商条款。

## 文献拓展与报告

PubMed ELink 提供相似、参考与被引关系；支持 1–3 跳、每条路径 1–20 篇、每任务最多新增 100 篇。自动去重并保存边来源。PubMed 引文覆盖不完整，空结果不代表没有引用。独立导入的 PDF 没有 PMID，需先在 PubMed 检索对应记录再关联 PDF。

报告选择 2–20 篇：逐篇证据卡 → 对比研究特征与结果 → 生成主题综合、局限性和研究空白，附选文清单与证据范围。这是初步叙述性综述，不是系统综述，不执行统计 meta 分析。

PDF 限制 60 MB、500 页。扫描件不自动 OCR，图像与复杂表格可能遗漏。长文档按页分块，问答使用词项匹配；中文对英文全文的词法匹配效果有限。界面明确标注摘要或文本摘录。引用页码是 PDF 文件页码。

笔记自动保存到 SQLite，浏览器 localStorage 保留未保存草稿；关闭页面前提醒未保存内容。版本号检测多标签修改冲突，发生冲突请先复制草稿，再重新打开。

## 导出与备份

笔记及报告可导出 Markdown、PDF、Word (.docx)。支持中文、标题、段落、列表和表格。Word/PDF 不保证还原 Markdown 所有内联格式；不抓取远程图片。Markdown 导出保留源文本。

默认数据路径可在设置查看：Windows 通常为 %LOCALAPPDATA%\paper-sa，macOS 为 ~/Library/Application Support/paper-sa，Linux 为 ~/.local/share/paper-sa。可用 PAPER_SA_HOME 或 --data-dir 修改。

PDF 在 papers/，数据库在 workspace.sqlite3，设置在 settings.json，专用浏览器登录态在 browser-profile/。退出程序后备份整个目录；不要公开上传。
