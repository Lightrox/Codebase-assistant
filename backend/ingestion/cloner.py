import os
import shutil
import tempfile
from urllib.parse import urlparse
from git import Repo
from git.exc import GitCommandError


def clone_repo(repo_url: str) -> dict:

    # Basic validation
    import re
    if not re.match(r"^https?://(www\.)?github\.com/", repo_url):
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    path_parts = [p for p in urlparse(repo_url).path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    owner = path_parts[0]
    repo_name = path_parts[1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # Create a unique temp directory for this repo
    temp_dir = tempfile.mkdtemp(prefix="codebase_assistant_")

    try:
        print(f"[Cloner] Cloning {repo_url} into {temp_dir}...")
        git_repo = Repo.clone_from(repo_url, temp_dir)
        commit_sha = git_repo.head.commit.hexsha
        print(f"[Cloner] Clone successful.")
        print(f"[Cloner] owner={owner} repo={repo_name} commit_sha={commit_sha}")
        return {
            "path": temp_dir,
            "owner": owner,
            "repo": repo_name,
            "commit_sha": commit_sha,
        }

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
