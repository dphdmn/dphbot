import os
import sys
import subprocess
import shutil

REPO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slidyreplay")
REPO_URL = "https://github.com/dphdmn/slidyreplay.git"


def is_git_repo(path: str) -> bool:
    git_dir = os.path.join(path, ".git")
    return os.path.isdir(git_dir)


def clone_repo() -> bool:
    print(f"[replay_init] Cloning {REPO_URL} into {REPO_DIR}...")
    try:
        result = subprocess.run(
            ["git", "clone", REPO_URL, REPO_DIR],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"[replay_init] Clone successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[replay_init] Clone failed: {e.stderr}")
        return False


def pull_latest() -> bool:
    print(f"[replay_init] Pulling latest changes in {REPO_DIR}...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=REPO_DIR,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"[replay_init] Pull successful: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[replay_init] Pull failed: {e.stderr}")
        return False


def init_replay_generator(force_update: bool = True) -> bool:
    if not os.path.exists(REPO_DIR):
        return clone_repo()
    
    if not is_git_repo(REPO_DIR):
        print(f"[replay_init] {REPO_DIR} exists but is not a git repo. Removing and re-cloning...")
        try:
            shutil.rmtree(REPO_DIR)
        except Exception as e:
            print(f"[replay_init] Failed to remove existing directory: {e}")
            return False
        return clone_repo()
    
    if force_update:
        return pull_latest()
    
    return True


def get_main_py_path() -> str:
    return os.path.join(REPO_DIR, "main.py")


def get_replay_video_module_path():
    if REPO_DIR not in sys.path:
        sys.path.insert(0, REPO_DIR)
    return REPO_DIR


if __name__ == "__main__":
    init_replay_generator(force_update=True)
