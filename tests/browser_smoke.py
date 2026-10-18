import io
import json
import socket
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from playwright.sync_api import expect, sync_playwright
from reportlab.pdfgen import canvas

from paper_sa.app import create_app
from paper_sa.browser import Browser
from paper_sa.config import Config
from paper_sa.store import Store


def main():
    output = Path("test-results").resolve()
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="browser-smoke-", dir=output) as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(output)
        original_workspace = root / "workspace-a"
        application = create_app(original_workspace, preferences_path=root / "preferences.json")
        fixtures = [
            {
                "pmid": "101001",
                "doi": "10.1000/trial-one",
                "title": "Cardiovascular outcomes in a randomized clinical trial",
                "journal": "Test Journal",
                "year": "2024",
                "authors": ["Smith J", "Lee A"],
                "abstract": "Test fixture: 120 adults randomized to intervention or placebo.",
                "publication_types": ["Randomized Controlled Trial"],
            },
            {
                "pmid": "101002",
                "doi": "10.1000/trial-two",
                "title": "A comparative study of long-term treatment outcomes",
                "journal": "Test Medicine",
                "year": "2025",
                "authors": ["Chen B"],
                "abstract": "Test fixture: comparative outcomes in adults.",
                "publication_types": ["Clinical Trial"],
            },
        ]

        async def search(*args, **kwargs):
            return {
                "query": "cardiovascular",
                "translation": "cardiovascular[All Fields]",
                "total": 2,
                "warnings": {},
                "papers": fixtures,
            }

        async def neighbors(*args, **kwargs):
            return [
                dict(
                    fixtures[0],
                    pmid="101003",
                    doi="10.1000/third",
                    title="Related evidence from a follow-up study",
                )
            ]

        async def complete(*args, **kwargs):
            passage = (
                "Secondary outcome evidence from page two."
                if "Secondary outcome evidence" in args[0]
                else "Test fixture: comparative outcomes in adults."
            )
            citation = "[P1 · p.2]" if "Secondary outcome evidence" in args[0] else "[P1 · 摘要]"
            return (
                "## 研究问题与 PICO\n\n这是浏览器测试中的模拟证据摘要，不是真实研究结论。\n\n"
                f"> **论文原文** {citation}\n>\n> {passage}\n\n"
                "**解读**：这里区分论文原句与 AI 解读。\n\n"
                "| 项目 | 内容 |\n|---|---|\n| 人群 | 120 adults |\n\n## 局限性\n\n需要核对原文。"
            )

        application.state.pubmed.search = search
        application.state.pubmed.neighbors = neighbors
        application.state.llm.complete = complete
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _attempt in range(100):
            if server.started:
                break
            time.sleep(0.05)
        errors = []
        try:
            with sync_playwright() as driver:
                browser = driver.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}")
                expect(page.get_by_role("heading", name="文献工作台", exact=True)).to_be_visible()
                page.screenshot(path=output / "workspace-empty.png", full_page=True)
                page.locator("#search-query").fill("cardiovascular")
                page.locator("#search-form").evaluate("form => form.requestSubmit()")
                expect(page.locator(".paper-card")).to_have_count(2)
                page.screenshot(path=output / "workspace-populated.png", full_page=True)
                page.locator(".nav-item[data-view=settings]").click()
                expect(page.locator("#settings-form")).to_be_visible()
                page.locator("#api-key").fill("test-placeholder")
                page.locator('[name="auto_summarize"]').uncheck()
                page.locator("#settings-form").evaluate("form => form.requestSubmit()")
                expect(page.get_by_text("设置已加密保存到本地。")).to_be_visible()
                page.locator(".nav-item[data-view=library]").click()
                expect(page.locator(".paper-card")).to_have_count(2)
                page.locator(".paper-title").filter(has_text=fixtures[1]["title"]).click()
                expect(page.get_by_role("heading", name="Abstract", exact=True)).to_be_visible()
                expect(page.locator(".reader-layout > section")).to_have_count(3)
                panels = page.locator(".reader-layout > section").evaluate_all(
                    "panels => panels.map(panel => {const rect = panel.getBoundingClientRect(); return {left: rect.left, top: rect.top, right: rect.right};})"
                )
                assert abs(panels[0]["top"] - panels[2]["top"]) < 2
                assert panels[0]["right"] <= panels[1]["left"] < panels[2]["left"]
                expect(page.locator("#note-editor")).to_have_count(0)
                page.locator('[data-action="summarize"]').click()
                expect(page.locator(".message.assistant")).to_have_count(1)
                expect(page.locator(".message.assistant .paper-original strong")).to_have_text("论文原文")
                passage = page.locator(".message.assistant .paper-original p").last
                original_text = passage.inner_text()
                selected_text = "comparative outcomes"
                passage.evaluate(
                    "(element, text) => {const start = element.textContent.indexOf(text); const range = document.createRange(); range.setStart(element.firstChild, start); range.setEnd(element.firstChild, start + text.length); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);}",
                    selected_text,
                )
                expect(page.locator("#chat-selection-toolbar")).to_be_visible()
                page.locator('[data-action="save-selection"]').click()
                expect(page.get_by_text("选中文字已添加到当前阅读笔记。")).to_be_visible()
                expect(page.locator("#note-editor")).to_be_visible()
                expect(page.locator("#chat-form")).to_be_visible()
                first_note = page.locator("#reader-note-select").input_value()
                content = application.state.store.note(first_note)["content"]
                assert selected_text in content
                assert original_text not in content
                assert "这里区分论文原句与 AI 解读" not in content
                assert "PMID 101002" in content and "[P1 · 摘要]" in content
                expect(page.locator("#chat-selection-toolbar")).to_be_hidden()
                page.locator(".message.user .message-content").evaluate(
                    "element => {const range = document.createRange(); range.selectNodeContents(element); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);}"
                )
                expect(page.locator("#chat-selection-toolbar")).to_be_hidden()
                page.locator('[data-action="reader-new-note"]').click()
                expect(page.locator("#reader-note-select option")).to_have_count(2)
                second_note = page.locator("#reader-note-select").input_value()
                assert first_note != second_note
                expect(page.locator("#note-editor")).not_to_have_value(content)
                page.locator("#reader-note-select").select_option(first_note)
                expect(page.locator("#note-editor")).to_have_value(content)
                page.locator("#note-editor").fill(
                    "# 浏览器验证笔记\n\n中文内容应自动保存。\n\n| 指标 | 结果 |\n|---|---|\n| 样本 | 120 |"
                )
                page.locator('[data-action="save-answer"]').click()
                expect(page.get_by_text("已保存到这篇论文的阅读笔记。")).to_be_visible()
                expect(page.locator("#save-state")).to_have_text("已保存到本地")
                content = page.locator("#note-editor").input_value()
                assert "中文内容应自动保存" in content
                assert "**论文原文**" in content
                assert selected_text in content
                assert "中文内容应自动保存" not in application.state.store.note(second_note)["content"]
                page.locator('[data-action="preview"]').click()
                expect(page.locator("#note-preview h1")).to_have_text("浏览器验证笔记")
                for format_name in ("md", "pdf", "docx"):
                    page.locator("#export-format").select_option(format_name)
                    with page.expect_download() as download_info:
                        page.locator('[data-action="export"]').click()
                    download_info.value.save_as(output / ("browser-note." + format_name))
                page.locator('[data-action="import-paper"]').click()
                pdf = io.BytesIO()
                document = canvas.Canvas(pdf)
                document.drawString(40, 740, "Browser test PDF. This is not a real study.")
                document.drawString(
                    40, 700, "120 adults. Study outcomes and clinical significance require verification."
                )
                document.showPage()
                document.drawString(40, 740, "Secondary outcome evidence from page two.")
                document.save()
                page.locator("#pdf-upload").set_input_files(
                    {"name": "trial.pdf", "mimeType": "application/pdf", "buffer": pdf.getvalue()}
                )
                expect(page.locator("#pdf-frame")).to_be_visible()
                expect(page.frame_locator("#pdf-frame").locator("#pdf-canvas")).to_have_attribute(
                    "data-ready", "true", timeout=20000
                )
                page.frame_locator("#pdf-frame").locator("#zoom-in").click()
                expect(page.frame_locator("#pdf-frame").locator("#pdf-canvas")).to_have_attribute(
                    "data-ready", "true"
                )
                page.frame_locator("#pdf-frame").locator("#fit").click()
                expect(page.frame_locator("#pdf-frame").locator("#pdf-canvas")).to_have_attribute(
                    "data-ready", "true"
                )
                expect(page.locator(".message.assistant")).to_have_count(1)
                expect(page.locator("#note-editor")).to_have_value(content)
                page.locator("#chat-question").fill("请给出第二页的论文原文")
                page.locator("#chat-form").evaluate("form => form.requestSubmit()")
                expect(page.locator(".message.assistant")).to_have_count(2)
                expect(page.locator("#note-editor")).to_have_value(content)
                original = page.locator(".message.assistant").last.locator(".paper-original")
                expect(original).to_contain_text("Secondary outcome evidence from page two.")
                original.locator('[data-action="pdf-page"]').click()
                expect(page.frame_locator("#pdf-frame").locator("#page-number")).to_have_value("2")
                paragraph = original.locator("p").last
                paragraph.scroll_into_view_if_needed()
                paragraph.evaluate(
                    "element => {const range = document.createRange(); range.selectNodeContents(element); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);}"
                )
                expect(page.locator("#chat-selection-toolbar")).to_be_visible()
                page.locator('[data-action="save-selection"]').click()
                expect(page.get_by_text("选中文字已添加到当前阅读笔记。")).to_be_visible()
                content = page.locator("#note-editor").input_value()
                assert "Secondary outcome evidence from page two." in content and "[P1 · p.2]" in content
                assert "中文内容应自动保存" in content
                page.reload()
                expect(page.locator("#note-editor")).to_have_value(content)
                expect(page.locator(".message.assistant")).to_have_count(2)
                expect(page.frame_locator("#pdf-frame").locator("#pdf-canvas")).to_have_attribute(
                    "data-ready", "true", timeout=20000
                )
                page.screenshot(path=output / "reader.png", full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator(".reader-notes").scroll_into_view_if_needed()
                expect(page.locator("#note-editor")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    "Reader mobile overflow"
                )
                page.screenshot(path=output / "reader-mobile.png", full_page=True)
                page.set_viewport_size({"width": 1440, "height": 1050})
                page.locator(".nav-item[data-view=library]").click()
                expect(page.locator(".paper-card")).to_have_count(2)
                page.locator("#select-all").check()
                page.locator('[data-action="snowball"]').click()
                page.locator("#snowball-form").evaluate("form => form.requestSubmit()")
                expect(page.locator(".badge.completed")).to_have_count(1)
                page.locator(".nav-item[data-view=graph]").click()
                expect(page.locator(".graph-node")).to_have_count(3)
                page.screenshot(path=output / "graph.png", full_page=True)
                page.locator(".nav-item[data-view=library]").click()
                expect(page.locator("#library-results")).to_be_visible()
                page.locator('[data-action="report"]').click()
                page.locator('#report-form [name="topic"]').fill("浏览器测试中的证据比较")
                page.locator("#report-form").evaluate("form => form.requestSubmit()")
                expect(page.locator(".badge.completed")).to_have_count(2)
                page.locator('[data-action="open-note"]').first.click()
                expect(page.locator("#note-title")).to_have_value("浏览器测试中的证据比较 · 综述初稿")
                page.screenshot(path=output / "report.png", full_page=True)
                page.locator(".nav-item[data-view=library]").click()
                page.set_viewport_size({"width": 390, "height": 844})
                expect(page.locator("#search-query")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    "Mobile horizontal overflow"
                )
                page.screenshot(path=output / "mobile.png", full_page=True)
                context.route(
                    "https://publisher.example.test/paper.pdf",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="test.pdf"'},
                        body=pdf.getvalue(),
                    ),
                )
                downloader = Browser(application.state.config)
                downloader._context = lambda: context
                destination = root / "verified-download.pdf"
                route_used = downloader._download(
                    [
                        {
                            "url": "https://publisher.example.test/paper.pdf",
                            "kind": "browser",
                            "label": "test publisher",
                        }
                    ],
                    destination,
                    threading.Event(),
                )
                assert route_used == "test publisher"
                assert destination.read_bytes() == pdf.getvalue()
                downloader.executor.shutdown()

                target_workspace = root / "研究 空间 B"
                Config(target_workspace)
                target_store = Store(target_workspace / "workspace.sqlite3")
                target_note = target_store.create_note("B 的笔记", "工作目录 B 的独立笔记")
                target_store.execute("UPDATE notes SET id=? WHERE id=?", (first_note, target_note["id"]))
                target_store.close()
                stale_page = context.new_page()
                stale_page.goto(f"http://127.0.0.1:{port}/#notes/{first_note}")
                expect(stale_page.locator("#note-editor")).to_be_visible()
                stale_page.route(
                    "**/api/notes/*",
                    lambda route: (
                        route.fulfill(status=503, json={"detail": "模拟临时保存失败"})
                        if route.request.method == "PUT"
                        else route.continue_()
                    ),
                )
                draft = "工作目录 A 未保存草稿，不可写入 B"
                stale_page.locator("#note-editor").fill(draft)
                expect(stale_page.locator("#save-state")).to_have_text("保存失败 · 草稿已保留")
                page.set_viewport_size({"width": 1440, "height": 1050})
                page.locator(".nav-item[data-view=settings]").click()
                expect(page.locator("#current-workspace")).to_have_text(str(original_workspace))
                page.locator('[data-action="switch-workspace"]').click()
                page.locator("#workspace-path").fill("relative/path")
                page.locator("#workspace-form").evaluate("form => form.requestSubmit()")
                expect(page.get_by_text("请填写完整的绝对路径，不能使用相对路径")).to_be_visible()
                page.locator("#workspace-path").fill(str(target_workspace))
                page.screenshot(path=output / "workspace-switch.png", full_page=True)
                page.locator("#workspace-form").evaluate("form => form.requestSubmit()")
                expect(page.get_by_text("工作目录已切换，原目录的数据保持不变。")).to_be_visible()
                expect(page.locator("#nav-count")).to_have_text("0")
                stale_page.unroute("**/api/notes/*")
                stale_page.locator("#note-editor").press("Control+s")
                expect(stale_page.locator("#workspace-stale")).to_be_visible()
                expect(stale_page.locator("#note-editor")).to_have_value(draft)
                assert application.state.store.note(first_note)["content"] == "工作目录 B 的独立笔记"
                page.locator(".nav-item[data-view=notes]").click()
                expect(page.locator("#note-editor")).to_have_value("工作目录 B 的独立笔记")
                page.reload()
                expect(page.locator("#note-editor")).to_have_value("工作目录 B 的独立笔记")
                page.locator(".nav-item[data-view=settings]").click()
                expect(page.locator("#current-workspace")).to_have_text(str(target_workspace))
                page.locator('[data-action="switch-workspace"]').click()
                assert str(original_workspace) in page.locator("#workspace-recent option").evaluate_all(
                    "options => options.map(option => option.value)"
                )
                page.locator("#workspace-path").fill(str(original_workspace))
                page.locator("#workspace-form").evaluate("form => form.requestSubmit()")
                expect(page.locator(".paper-card")).to_have_count(3)
                page.goto(f"http://127.0.0.1:{port}/#notes/{first_note}")
                expect(page.locator("#note-editor")).to_have_value(draft)
                page.locator("#note-editor").press("Control+s")
                expect(page.locator("#save-state")).to_have_text("已保存到本地")
                assert application.state.store.note(first_note)["content"] == draft
                stale_page.close()
                browser.close()
            assert not errors, errors
            print(
                json.dumps(
                    {"status": "passed", "browser_errors": errors, "screenshots": str(output)},
                    ensure_ascii=False,
                )
            )
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive(), "Test server did not shut down"


if __name__ == "__main__":
    main()
