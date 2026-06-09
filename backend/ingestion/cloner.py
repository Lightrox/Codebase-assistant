import os
import shutil
import tempfile
from git import Repo
from git.exc import GitCommandError


def clone_repo(repo_url: str) -> str:
    """
    Clones a GitHub repo to a temporary local directory.

    Args:
        repo_url: GitHub URL e.g. "https://github.com/user/repo"

    Returns:
        Local path where the repo is cloned e.g. "/tmp/abc123/repo"

    Raises:
        ValueError: if URL is not a valid GitHub URL
        RuntimeError: if cloning fails
    """

    # Basic validation
    import re
    if not re.match(r"^https?://(www\.)?github\.com/", repo_url):
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    # Create a unique temp directory for this repo
    temp_dir = tempfile.mkdtemp(prefix="codebase_assistant_")

    try:
        print(f"[Cloner] Cloning {repo_url} into {temp_dir}...")
        Repo.clone_from(repo_url, temp_dir)
        print(f"[Cloner] Clone successful.")
        return temp_dir

    except GitCommandError as e:
        # Clean up temp dir if clone failed
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repo: {e}")


def delete_repo(repo_path: str):
    """
    Deletes the cloned repo from disk to free up space.

    Args:
        repo_path: local path returned by clone_repo()
    """
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
        print(f"[Cloner] Deleted repo at {repo_path}")
