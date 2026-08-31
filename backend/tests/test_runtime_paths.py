from __future__ import annotations

from pathlib import Path

from app.config import BACKEND_ROOT, Settings


def test_relative_runtime_paths_are_resolved_from_backend_root():
    settings = Settings(
        storage_mode="sqlite",
        sqlite_path="../local-data/processagent.db",
        vector_backend="chroma",
        chroma_path="../local-data/chroma",
    )
    assert Path(settings.sqlite_path) == (BACKEND_ROOT / "../local-data/processagent.db").resolve()
    assert Path(settings.chroma_path) == (BACKEND_ROOT / "../local-data/chroma").resolve()
