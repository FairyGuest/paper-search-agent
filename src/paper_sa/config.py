import json
import os
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from platformdirs import user_data_path
from pydantic import BaseModel, Field, field_validator

PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-5"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
    },
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
    "custom": {"base_url": "https://api.example.com/v1", "model": ""},
}


class Settings(BaseModel):
    provider: str = "openai"
    base_url: str = PROVIDERS["openai"]["base_url"]
    model: str = PROVIDERS["openai"]["model"]
    api_key: str = Field(default="", max_length=4096)
    ncbi_api_key: str = Field(default="", max_length=1024)
    contact_email: str = Field(default="", max_length=254)
    browser_mode: str = "managed"
    cdp_url: str = "http://127.0.0.1:9222"
    auto_summarize: bool = True
    context_chars: int = Field(default=32000, ge=8000, le=100000)

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value):
        if value not in PROVIDERS:
            raise ValueError("未知模型提供商")
        return value

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value):
        parsed = urlparse(value)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("请输入不含密钥、查询参数的 API Base URL")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("远程 API 必须使用 HTTPS；本机 API 可以使用 HTTP")
        return value.rstrip("/")

    @field_validator("cdp_url")
    @classmethod
    def valid_cdp(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("仅允许连接本机 Chrome 调试端口")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("无效的 Chrome 调试地址")
        return value.rstrip("/")

    @field_validator("browser_mode")
    @classmethod
    def valid_browser(cls, value):
        if value not in {"managed", "cdp", "manual"}:
            raise ValueError("未知浏览器模式")
        return value

    @field_validator("contact_email")
    @classmethod
    def valid_email(cls, value):
        if value and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("请输入有效联系邮箱，用于 Unpaywall / NCBI")
        return value.strip()


class Config:
    def __init__(self, root: Path | None = None):
        self.root = Path(
            root or os.environ.get("PAPER_SA_HOME") or user_data_path("paper-sa", appauthor=False)
        ).resolve()
        self.workspace_id = sha256(str(self.root).encode()).hexdigest()[:24]
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in ("papers", "staging", "browser-profile"):
            (self.root / folder).mkdir(exist_ok=True)
        self.path = self.root / "settings.json"
        key_path = self.root / ".secret.key"
        if not key_path.exists():
            with key_path.open("xb") as handle:
                handle.write(Fernet.generate_key())
            key_path.chmod(0o600)
        self.cipher = Fernet(key_path.read_bytes())
        self.settings = self._load()

    def _load(self):
        if not self.path.exists():
            return Settings()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for key in ("api_key", "ncbi_api_key"):
            if data.get(key):
                data[key] = self.cipher.decrypt(data[key].encode()).decode()
        return Settings.model_validate(data)

    def save(self, changes: dict):
        data = self.settings.model_dump()
        target_changed = any(changes.get(key, data[key]) != data[key] for key in ("provider", "base_url"))
        if target_changed:
            data["api_key"] = ""
        for key in ("api_key", "ncbi_api_key"):
            if changes.get(key) == "":
                changes.pop(key)
            if changes.pop(f"clear_{key}", False):
                changes[key] = ""
        data.update(changes)
        settings = Settings.model_validate(data)
        encoded = settings.model_dump()
        for key in ("api_key", "ncbi_api_key"):
            if encoded[key]:
                encoded[key] = self.cipher.encrypt(encoded[key].encode()).decode()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(encoded, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.path)
        self.settings = settings
        return self.public()

    def public(self):
        result = self.settings.model_dump(exclude={"api_key", "ncbi_api_key"})
        result.update(
            has_api_key=bool(self.settings.api_key), has_ncbi_api_key=bool(self.settings.ncbi_api_key)
        )
        result["data_dir"] = str(self.root.resolve())
        result["workspace_id"] = self.workspace_id
        result["providers"] = PROVIDERS
        return result
