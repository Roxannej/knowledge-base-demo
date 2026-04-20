"""
索引生命周期管理：创建、加载、删除、列举索引，并统一管理索引元数据。
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field

from .faiss_store import FaissPersistedVectorStore

_REGISTRY_FILE = "index_registry.json"
_DEFAULT_INDEX_NAME = "default"
_INDEX_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IndexRegistryItem(BaseModel):
    """索引注册信息（持久化到 registry）。"""

    name: str
    description: str = ""
    created_at: str
    updated_at: str


class IndexInfo(BaseModel):
    """索引公开信息（API 返回使用）。"""

    name: str
    description: str = ""
    document_count: int = Field(ge=0)
    updated_at: str


class IndexAlreadyExistsError(ValueError):
    pass


class IndexNotFoundError(ValueError):
    pass


class InvalidIndexNameError(ValueError):
    pass


class IndexManager:
    """管理多索引目录、注册表与向量库实例缓存。"""

    def __init__(self, root_dir: Path | str) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._stores: Dict[str, FaissPersistedVectorStore] = {}
        self._registry = self._load_registry()
        self._ensure_default_index()

    def _validate_name(self, name: str) -> str:
        value = (name or "").strip()
        if not _INDEX_NAME_RE.match(value):
            raise InvalidIndexNameError(
                "index_name 仅允许字母、数字、下划线和中划线，长度 1-64。"
            )
        return value

    def _registry_path(self) -> Path:
        return self.root_dir / _REGISTRY_FILE

    def _index_dir(self, name: str) -> Path:
        return self.root_dir / name

    def _load_registry(self) -> Dict[str, IndexRegistryItem]:
        path = self._registry_path()
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        out: Dict[str, IndexRegistryItem] = {}
        for item in raw:
            try:
                parsed = IndexRegistryItem.model_validate(item)
            except Exception:
                continue
            out[parsed.name] = parsed
        return out

    def _save_registry(self) -> None:
        payload = [item.model_dump() for item in sorted(self._registry.values(), key=lambda x: x.name)]
        self._registry_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_default_index(self) -> None:
        if _DEFAULT_INDEX_NAME in self._registry:
            return
        now = _utc_now_iso()
        self._registry[_DEFAULT_INDEX_NAME] = IndexRegistryItem(
            name=_DEFAULT_INDEX_NAME,
            description="Default knowledge base index",
            created_at=now,
            updated_at=now,
        )
        self._save_registry()

    def get_store(self, name: str = _DEFAULT_INDEX_NAME) -> FaissPersistedVectorStore:
        index_name = self._validate_name(name)
        if index_name not in self._registry:
            raise IndexNotFoundError(f"索引不存在: {index_name}")
        cached = self._stores.get(index_name)
        if cached is not None:
            return cached
        store = FaissPersistedVectorStore(self._index_dir(index_name))
        self._stores[index_name] = store
        return store

    def create_index(self, *, name: str, description: str = "") -> IndexInfo:
        index_name = self._validate_name(name)
        if index_name in self._registry:
            raise IndexAlreadyExistsError(f"索引已存在: {index_name}")
        now = _utc_now_iso()
        self._registry[index_name] = IndexRegistryItem(
            name=index_name,
            description=(description or "").strip(),
            created_at=now,
            updated_at=now,
        )
        self._save_registry()
        # 触发目录创建，保证创建后可见
        self.get_store(index_name)
        return self.get_index(index_name)

    def delete_index(self, name: str) -> None:
        index_name = self._validate_name(name)
        if index_name not in self._registry:
            raise IndexNotFoundError(f"索引不存在: {index_name}")
        self._stores.pop(index_name, None)
        self._registry.pop(index_name, None)
        self._save_registry()
        shutil.rmtree(self._index_dir(index_name), ignore_errors=True)

    def touch_index(self, name: str) -> None:
        index_name = self._validate_name(name)
        item = self._registry.get(index_name)
        if item is None:
            return
        item.updated_at = _utc_now_iso()
        self._registry[index_name] = item
        self._save_registry()

    def get_index(self, name: str) -> IndexInfo:
        index_name = self._validate_name(name)
        item = self._registry.get(index_name)
        if item is None:
            raise IndexNotFoundError(f"索引不存在: {index_name}")
        store = self.get_store(index_name)
        return IndexInfo(
            name=item.name,
            description=item.description,
            document_count=store.size,
            updated_at=item.updated_at,
        )

    def list_indexes(self) -> list[IndexInfo]:
        out: list[IndexInfo] = []
        for name in sorted(self._registry.keys()):
            try:
                out.append(self.get_index(name))
            except IndexNotFoundError:
                continue
        return out
