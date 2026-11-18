"""Assemble a local copy of the pinned upstream project with the procurement PoC."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
UPSTREAM = "https://github.com/lalala613lys/ai-solution-copilot.git"
BASE_COMMIT = "16934a4ebf844b12720c97e6f41add46da4415da"


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def main() -> int:
    workspace = ROOT / "workspace"
    if workspace.exists() or workspace.is_symlink():
        print(f"本地工作目录已存在，请直接使用 {workspace}", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix=".setup-", dir=ROOT) as staging:
            stage = Path(staging).resolve()
            checkout = stage / "upstream"
            git("clone", "--quiet", "--no-checkout", "--no-tags", UPSTREAM, str(checkout), cwd=stage)
            git("checkout", "--quiet", "--detach", BASE_COMMIT, cwd=checkout)
            patch = str(ROOT / "integration.patch")
            git("apply", "--check", "--unidiff-zero", patch, cwd=checkout)
            git("apply", "--unidiff-zero", patch, cwd=checkout)
            shutil.copytree(ROOT / "overlay", checkout, dirs_exist_ok=True)

            if stage.parent != ROOT or checkout.resolve().parent != stage:
                raise OSError("临时工作目录不在项目目录下")
            checkout.rename(workspace)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"组装失败。{exc}", file=sys.stderr)
        return 1

    print(f"组装完成，请从 {workspace} 下的 backend 和 frontend 启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
