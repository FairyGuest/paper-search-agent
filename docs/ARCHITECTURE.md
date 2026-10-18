# 架构与安全边界

## 本地工作流 Agent

FastAPI 同时提供网页与 JSON API，SQLite WAL 存储元数据、页文本、关系、消息、笔记、检索日志和任务。随包分发的 PDF.js 本地渲染 PDF，支持翻页、缩放、适宽与引用页码跳转；原始 PDF 端点支持 Range。无需 Node.js、额外数据库或向量服务。

Agent 使用受控编排，而不是让大模型任意执行 shell：

1. 检索规划：可选 LLM 生成查询，用户检查后执行。
2. 检索与关联：ESearch / EFetch 获取真实记录，ELink 有界 BFS 拓展。
3. 下载：PMC / DOI / Crossref / Unpaywall 解析路由，同域分组、串行可见浏览器下载与 PDF 校验。
4. 阅读：逐页分块、词法检索、上下文限制、证据范围与页码标签。
5. 综述：每篇证据卡、跨论文综合、程序附加来源清单、保存可编辑初稿。

控制层负责去重、权限、取消与持久化；LLM 仅生成查询建议与证据文本。状态有 queued、running、waiting_user、completed、needs_action、failed、cancelled、interrupted。重启后未完成任务标记为 interrupted，需重新执行，不伪装恢复。取消在当前网络/模型请求返回后生效，已发生请求仍可能计费。

## 上游 skill 适配

不是直接执行上游 macOS AppleScript，而是跨平台重实现其流程。保留合法浏览器授权、元数据路由、域分组、验证归档、人工介入。加入专用可见浏览器、CDP、手动模式。不自动点击验证码、不读取或填写账号密码，不用无登录态无头浏览器假冒机构授权。

归档命名为“年份_期刊_第一作者_标题_唯一ID.pdf”，避免覆盖。手动模式不扫描用户 Downloads。更多来源信息见 THIRD_PARTY.md。

## 安全与隐私

- 只绑定 loopback，检查 Host/Origin，拦截跨站请求；随机进程 token 保护 API，PDF 单独使用 HttpOnly SameSite cookie，不启用 CORS。
- CSP 与 Markdown 活动内容过滤；不加载远程图片，文献文本不作为工具指令执行。
- 模型与 NCBI Key 由 Fernet 加密，解密密钥在同一 OS 用户数据目录。这降低明文误泄露风险，但不能抵御同账户恶意程序、管理员或完整目录泄露，不是硬件密钥库。
- Key 不回显，错误不包含完整上游响应或认证头；变更模型目标清除旧 Key。
- PDF、笔记、数据库仍是明文；不应处理可识别患者信息。
- AI 请求发送文献片段、最近对话或证据卡给选定模型；公开查询发送至 NCBI，DOI 路由解析可能发送至 Crossref / Unpaywall。
- OA HTTP 下载逐跳检查公开地址、拒绝私网与 loopback；并非抵御恶意 DNS 的完整网络隔离。浏览器加载出版商资源，不是恶意网站沙箱。

这是个人本地工具，不应反向代理到公网。团队部署需要另行实现身份认证、权限隔离、服务级任务队列和资源限制。
