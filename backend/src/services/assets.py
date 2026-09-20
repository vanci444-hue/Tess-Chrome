"""图片通过报告或会话关系授权；路径只能位于专用上传目录。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from src.config.settings import Settings
from src.db.models import Asset, Report, Session
from src.models.contracts import BusinessError
from src.repositories.store import Store


class AssetService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def resolve(self, asset_id: str, session_id: str | None = None,
                      report_id: str | None = None) -> tuple[Path, str, str]:
        asset = await self.store.get(Asset, asset_id)
        allowed = False
        if asset and session_id:
            await self.store.require(Session, session_id)
            allowed = asset.session_id == session_id
        if asset and report_id:
            report = await self.store.get(Report, report_id)
            allowed = bool(report and asset_id in report.snapshot["asset_ids"] and
                           asset.session_id == report.session_id and report_id in asset.report_refs)
        if not asset or not allowed:
            raise BusinessError("报告资源不存在", "ASSET_NOT_FOUND", 404, "ASSET_NOT_FOUND")
        path = (self.config.upload_path / asset.relative_path).resolve()
        if not path.is_relative_to(self.config.upload_path) or not path.is_file() or asset.mime not in {
                "image/png", "image/jpeg", "image/webp"}:
            raise BusinessError("报告资源不存在", "ASSET_NOT_FOUND", 404, "ASSET_NOT_FOUND")
        with path.open("rb") as image:
            actual_hash = hashlib.file_digest(image, "sha256").hexdigest()
        if actual_hash != asset.sha256:
            raise BusinessError("报告资源校验失败，请重新获取图片", "ASSET_CHANGED", 404, "ASSET_NOT_FOUND")
        return path, asset.mime, asset.sha256
