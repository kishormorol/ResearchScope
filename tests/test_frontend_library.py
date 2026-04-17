from pathlib import Path
import subprocess


def test_frontend_library_node_suite():
    repo_root = Path(__file__).resolve().parent.parent
    test_file = repo_root / "tests" / "frontend" / "library.test.js"
    result = subprocess.run(
        ["node", "--test", str(test_file)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "Node library tests failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
