import asyncio
import json
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

from .network import ServiceError, public_url


class Browser:
    def __init__(self, config):
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paper-browser")
        self.driver = None
        self.browser = None
        self.context = None
        self.page = None
        self.mode = None
        self.stop = threading.Event()

    def _context(self):
        from playwright.sync_api import sync_playwright

        settings = self.config.settings
        signature = (settings.browser_mode, settings.cdp_url)
        if self.context is not None and signature == self.mode:
            try:
                self.context.cookies()
                return self.context
            except Exception:
                self._close()
        elif self.context is not None:
            self._close()
        self.stop.clear()
        self.driver = sync_playwright().start()
        self.mode = signature
        try:
            if settings.browser_mode == "cdp":
                self.browser = self.driver.chromium.connect_over_cdp(settings.cdp_url, timeout=15000)
                if not self.browser.contexts:
                    raise ServiceError("Chrome 未提供可连接的浏览器配置")
                self.context = self.browser.contexts[0]
            else:
                profile = self.config.root / "browser-profile"
                preferences = profile / "Default" / "Preferences"
                preferences.parent.mkdir(exist_ok=True)
                data = json.loads(preferences.read_text("utf-8")) if preferences.exists() else {}
                data.setdefault("plugins", {})["always_open_pdf_externally"] = True
                preferences.write_text(json.dumps(data), encoding="utf-8")
                options = {
                    "user_data_dir": str(profile),
                    "headless": False,
                    "accept_downloads": True,
                    "downloads_path": str(self.config.root / "staging"),
                    "timeout": 25000,
                }
                try:
                    self.context = self.driver.chromium.launch_persistent_context(channel="chrome", **options)
                except Exception:
                    self.context = self.driver.chromium.launch_persistent_context(**options)
            return self.context
        except Exception:
            self._close()
            raise ServiceError(
                "浏览器启动失败。运行 paper-sa install-browser，或选择手动模式/CDP；检查 Chrome 是否占用专用配置。"
            ) from None

    def _page(self):
        context = self._context()
        if self.page is None or self.page.is_closed():
            self.page = context.new_page()
        return self.page

    def _open(self, url):
        if self.config.settings.browser_mode == "manual":
            webbrowser.open(url)
            return
        page = self._page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            pass
        page.bring_to_front()

    async def open(self, url):
        await public_url(url)
        await asyncio.get_running_loop().run_in_executor(self.executor, self._open, url)

    def _download(self, routes, destination, cancelled):
        page = self._context().new_page()
        downloads = []
        watched = []
        completed = False

        def attach(target):
            target.on("download", receive)
            target.on("popup", attach)
            watched.append(target)

        def receive(download):
            downloads.append(download)

        attach(page)
        try:
            for route in routes[:4]:
                if self.stop.is_set() or cancelled.is_set():
                    return None
                try:
                    page.goto(route["url"], wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                deadline = time.monotonic() + (60 if route["kind"] == "article" else 25)
                clicked = False
                while time.monotonic() < deadline:
                    if self.stop.is_set() or cancelled.is_set():
                        return None
                    if downloads:
                        download = downloads.pop(0)
                        if download.failure():
                            continue
                        download.save_as(destination)
                        completed = True
                        return route["label"]
                    if not clicked and route["kind"] == "article":
                        links = page.locator(
                            'a:has-text("Download PDF"), a:has-text("View PDF"), a:has-text("Open the PDF"), a[href$=".pdf"]'
                        )
                        if links.count():
                            try:
                                links.first.click(timeout=2000)
                            except Exception:
                                pass
                            clicked = True
                    page.wait_for_timeout(500)
            return None
        finally:
            for target in watched:
                target.remove_listener("download", receive)
                target.remove_listener("popup", attach)
                if completed and not target.is_closed():
                    target.close()

    async def download(self, routes, destination, cancelled):
        for route in routes:
            await public_url(route["url"])
        if self.config.settings.browser_mode == "manual":
            if routes:
                await self.open(routes[0]["url"])
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(
                self.executor, self._download, routes, destination, cancelled
            )
        except ServiceError:
            raise
        except Exception:
            raise ServiceError("浏览器下载中断。请确认浏览器仍打开，登录后重试或手动导入 PDF。") from None

    def _close(self):
        if self.context is not None and self.mode and self.mode[0] != "cdp":
            try:
                self.context.close()
            except Exception:
                pass
        if self.driver is not None:
            try:
                self.driver.stop()
            except Exception:
                pass
        self.driver = self.context = self.page = self.browser = None

    async def close(self):
        self.stop.set()
        await asyncio.get_running_loop().run_in_executor(self.executor, self._close)
        self.executor.shutdown(wait=False, cancel_futures=True)
