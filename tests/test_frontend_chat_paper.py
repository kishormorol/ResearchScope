from __future__ import annotations

import subprocess
from pathlib import Path


def test_frontend_chat_paper_node_suite():
    repo_root = Path(__file__).resolve().parents[1]
    test_file = repo_root / "tests" / "frontend" / "chat-paper.test.js"
    result = subprocess.run(
        ["node", str(test_file)], cwd=repo_root, capture_output=True, text=True
    )
    assert result.returncode == 0, (
        "Node chat-paper tests failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
