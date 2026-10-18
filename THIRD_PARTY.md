# 上游参考

浏览器下载流程参考 browser-paper-download，作者 operoncao123：

https://github.com/operoncao123/browser-paper-download

阅读了 SKILL.md、README.md、references/publisher_patterns.md，参考了 scripts/lookup_ids.py 与 scripts/download_papers.py。上游许可证为 MIT（以该仓库 LICENSE 为准），查阅日期 2026-10-14。

本项目没有原样打包上游脚本；用 Python / Playwright 重实现流程，替代 macOS AppleScript，并增加本地服务与前端。主要区别是专用浏览器首次手动登录、验证码仅人工处理，以及不自动扫描 Downloads。

PubMed/NCBI、Crossref、Unpaywall、各出版商和模型提供商是独立第三方服务，应遵守各自使用条款与数据政策。论文版权不随本工具授予。

## PDF.js

PDF 阅读器包含 Mozilla PDF.js / pdfjs-dist 6.4.299（Apache-2.0）。源码与字体等附属资源的许可保留在 src/paper_sa/static/vendor/pdfjs/，第三方文件保留原版权信息。

官方仓库：https://github.com/mozilla/pdf.js

分发包来自 npm registry，scripts/vendor_pdfjs.py 校验固定 SHA-512 后仅提取指定运行时资源。最终用户不需要 Node.js 或在线 CDN。更新资源应同时更新脚本中的版本和完整性校验值。
