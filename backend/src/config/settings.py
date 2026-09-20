"""配置仅由项目文件读取；空 Key 允许本地业务启动。"""
from pathlib import Path

from pydantic import Field, model_validator

from pycore.core import BaseSettings, ConfigManager

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8099
    debug: bool = True
    database_path: str = "data/tess-chrome.db"
    upload_dir: str = "data/uploads"
    report_origin: str = "http://127.0.0.1:8099"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5199", "http://127.0.0.1:5199",
        "http://localhost:5175", "http://127.0.0.1:5175",
    ])
    allowed_extension_origin: str = "chrome-extension://ejbpocfjkdofijfgehnnhdnnhigkekdn"
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "::1"])
    bailian_base_url: str = ""
    bailian_api_key: str = ""
    llm_model: str = "qwen3.7-plus"
    asr_model: str = "qwen3-asr-flash-realtime"
    bailian_asr_ws_url: str = ""
    asr_connect_timeout: float = 10
    asr_finish_timeout: float = 10
    asr_sample_rate: int = 16000
    asr_chunk_ms: int = 100
    asr_buffer_seconds: int = 2
    asr_vad_threshold: float = 0.0
    asr_vad_silence_ms: int = 400
    asr_session_max_seconds: int = 300
    asr_connect_ttl_seconds: int = 60
    llm_enable_thinking: bool = False
    amap_web_service_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    map_radius_m: int = 5000
    map_station_limit: int = 3
    map_image_width: int = Field(default=750, ge=1, le=1024)
    map_image_height: int = Field(default=300, ge=1, le=1024)
    map_image_max_bytes: int = Field(default=5242880, ge=1)
    map_page_size: int = Field(default=20, ge=1)
    energy_max_years: int = Field(default=100, ge=1)
    http_connect_timeout: float = 5
    map_timeout: float = 10
    model_timeout: float = 60
    run_timeout: float = 180
    max_model_rounds: int = 6
    max_tool_calls: int = 10
    run_poll_interval_ms: int = 1000
    capture_stable_ms: int = 500
    max_text_chars: int = 12000
    list_page_size: int = 20
    list_max_page_size: int = 50
    max_active_captures: int = 3
    max_questions_per_round: int = 3
    default_phone_region: str = "CN"
    max_nickname_chars: int = 80
    max_email_chars: int = 254
    max_request_bytes: int = 262144
    frontend_dist: str = "frontend/dist"

    @model_validator(mode="after")
    def validate_local_settings(self):
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("本地 Demo 仅允许 loopback 绑定")
        return self

    @property
    def origins(self) -> list[str]:
        values = [*self.cors_origins, self.report_origin]
        if self.allowed_extension_origin:
            values.append(self.allowed_extension_origin)
        return list(dict.fromkeys(values))

    @property
    def database_url(self) -> str:
        path = Path(self.database_path)
        path = path if path.is_absolute() else BACKEND_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path.resolve()}"

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        return (path if path.is_absolute() else BACKEND_ROOT / path).resolve()


def load_settings() -> Settings:
    manager = ConfigManager[Settings]()
    manager.load(Settings, str(BACKEND_ROOT / ".env"), use_env=False)
    return manager.settings


settings = load_settings()
