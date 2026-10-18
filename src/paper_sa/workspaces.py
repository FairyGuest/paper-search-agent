import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from platformdirs import user_config_path, user_data_path

from .agents import Agents
from .browser import Browser
from .config import Config
from .llm import LLM
from .pubmed import PubMed
from .store import Store


class WorkspaceRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or user_config_path("paper-sa", appauthor=False) / "workspaces.json"

    def read(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("recent", []), list):
                raise ValueError
            paths = [data.get("current", ""), *data.get("recent", [])]
            if any(not isinstance(path, str) or (path and not Path(path).is_absolute()) for path in paths):
                raise ValueError
            return data
        except (ValueError, TypeError):
            raise ValueError("工作目录记录损坏，请备份并检查 workspaces.json") from None

    def startup_path(self, explicit: Path | None = None):
        selected = explicit or os.environ.get("PAPER_SA_HOME") or self.read().get("current")
        return Path(selected or user_data_path("paper-sa", appauthor=False)).expanduser().resolve()

    def public(self, current: Path):
        data = self.read()
        return {
            "default_dir": data.get("current", ""),
            "recent": list(dict.fromkeys([str(current), *data.get("recent", [])]))[:8],
        }

    def remember(self, root: Path, previous: Path | None = None):
        recent = list(dict.fromkeys([str(root), *self.public(previous or root)["recent"]]))[:8]
        data = {"current": str(root), "recent": recent}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def validate_workspace(value: str, current: Path):
    if not value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("请输入有效的工作目录绝对路径")
    root = Path(value.strip()).expanduser()
    if not root.is_absolute():
        raise ValueError("请填写完整的绝对路径，不能使用相对路径")
    root = root.resolve()
    if root == current:
        return root
    if root == root.parent or root.is_relative_to(current) or current.is_relative_to(root):
        raise ValueError("请选择独立目录，不要使用磁盘根目录或当前工作目录的父目录、子目录")
    if root.exists():
        if not root.is_dir():
            raise ValueError("目标是文件，请选择文件夹")
        if any(child.name != ".paper-sa.lock" for child in root.iterdir()):
            if not (root / "workspace.sqlite3").is_file() or not (root / ".secret.key").is_file():
                raise ValueError("目标非空且不是 Paper SA 工作目录，请选择空目录或已有工作目录")
            with closing(
                sqlite3.connect((root / "workspace.sqlite3").as_uri() + "?mode=ro", uri=True)
            ) as connection:
                tables = {
                    row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if not {"papers", "pages", "edges", "searches", "notes", "messages", "jobs"} <= tables:
                    raise ValueError("目标数据库不是完整的 Paper SA 工作目录")
    return root


class WorkspaceLock:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.handle = (root / ".paper-sa.lock").open("a+b")
        try:
            if self.handle.tell() == 0:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise ValueError("工作目录正被其他 Paper SA 实例占用，或无法锁定；请关闭该实例后重试") from None

    def close(self):
        self.handle.close()


class Workspace:
    def __init__(self, root: Path):
        self.lock = WorkspaceLock(root)
        self.store = None
        try:
            self.config = Config(root)
            self.store = Store(root / "workspace.sqlite3")
            self.pubmed, self.llm, self.browser = PubMed(self.config), LLM(self.config), Browser(self.config)
            self.agents = Agents(self.store, self.config, self.pubmed, self.llm, self.browser)
        except Exception:
            if self.store is not None:
                self.store.close()
            self.lock.close()
            raise

    async def close(self):
        try:
            await self.agents.shutdown()
        finally:
            try:
                self.store.close()
            finally:
                self.lock.close()
