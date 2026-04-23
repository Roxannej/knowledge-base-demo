from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import deps
from app.main import app


def _reset_index_manager(tmp_path: Path) -> None:
    os.environ["RAG_FAISS_INDEX_ROOT"] = str(tmp_path / "indexes")
    deps._index_manager = None


def test_health_endpoint_returns_ok(tmp_path: Path) -> None:
    _reset_index_manager(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "indexes" in data
    assert any(item["name"] == "default" for item in data["indexes"])


def test_index_lifecycle_create_list_get_delete(tmp_path: Path) -> None:
    _reset_index_manager(tmp_path)
    with TestClient(app) as client:
        create_resp = client.post(
            "/indexes",
            json={"name": "day7demo", "description": "day-07 smoke test"},
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["name"] == "day7demo"
        assert created["description"] == "day-07 smoke test"

        list_resp = client.get("/indexes")
        assert list_resp.status_code == 200
        names = {item["name"] for item in list_resp.json()}
        assert "default" in names
        assert "day7demo" in names

        get_resp = client.get("/indexes/day7demo")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "day7demo"

        delete_resp = client.delete("/indexes/day7demo")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

        get_after_delete = client.get("/indexes/day7demo")
        assert get_after_delete.status_code == 404
