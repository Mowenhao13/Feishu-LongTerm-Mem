"""
清空 data 目录下的记忆数据并重新初始化存储

操作步骤:
  1. 停止所有正在运行的 main.py 进程
  2. 删除 data/decisions/、data/objections/、data/archive/ 等记忆数据文件
  3. 删除 data/.git 重新初始化 Git 仓库
  4. 保留 data/docs/ 文档目录
"""

import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("reset_data")


def stop_main_processes() -> None:
    """停止所有正在运行的 main.py 进程"""
    logger.info("[Step 1/4] Stopping running main.py processes...")
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=10
        )
        killed = 0
        for line in result.stdout.splitlines():
            if "main.py" in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = int(parts[1])
                    try:
                        os.kill(pid, signal.SIGTERM)
                        logger.info("  Stopped PID %d", pid)
                        killed += 1
                    except ProcessLookupError:
                        pass

        if killed:
            time.sleep(2)

        for line in result.stdout.splitlines():
            if "main.py" in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = int(parts[1])
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logger.info("  Force killed PID %d", pid)
                    except ProcessLookupError:
                        pass

        logger.info("  Stopped %d process(es)", killed)
    except Exception as e:
        logger.warning("  Failed to stop processes: %s", e)


def clean_data_directory() -> None:
    """清理 data 目录下的记忆数据，保留 docs/"""
    logger.info("[Step 2/4] Cleaning memory data from data/...")

    keep_dirs = {"docs", ".git"}
    deleted_dirs = 0
    deleted_files = 0

    for entry in DATA_DIR.iterdir():
        if entry.name in keep_dirs:
            continue

        if entry.is_dir():
            shutil.rmtree(entry)
            logger.info("  Deleted directory: %s", entry.name)
            deleted_dirs += 1
        elif entry.is_file():
            entry.unlink()
            logger.info("  Deleted file: %s", entry.name)
            deleted_files += 1

    logger.info("  Removed %d dir(s) and %d file(s)", deleted_dirs, deleted_files)


def reset_git_repo() -> None:
    """删除 .git 目录，让 GitStorage 重新初始化"""
    logger.info("[Step 3/4] Resetting Git repository...")
    git_dir = DATA_DIR / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
        logger.info("  Deleted .git directory")
    else:
        logger.info("  No .git directory found")


def reinitialize_storage() -> None:
    """重新初始化 Git 存储，创建基础文件"""
    logger.info("[Step 4/4] Reinitializing Git storage...")

    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    from src.storage.git_storage import GitStorage, GitStorageConfig

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    storage = GitStorage(config=GitStorageConfig(
        work_dir=str(DATA_DIR),
    ))
    logger.info("  GitStorage reinitialized at %s", DATA_DIR)
    logger.info("  Base files: L0_RULES.md, dummy.md")


def main() -> None:
    logger.info("=" * 60)
    logger.info("  Resetting memory data in %s", DATA_DIR)
    logger.info("=" * 60)

    stop_main_processes()
    clean_data_directory()
    reset_git_repo()
    reinitialize_storage()

    logger.info("-" * 60)
    logger.info("  Reset complete! data/ is ready for fresh start.")
    logger.info("  Run 'uv run python main.py' to start the system.")
    logger.info("-" * 60)


if __name__ == "__main__":
    main()