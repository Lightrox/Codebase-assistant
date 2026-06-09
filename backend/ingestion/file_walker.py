import os

# File extensions we support
SUPPORTED_EXTENSIONS = {".py", ".java", ".js", ".ts", ".go", ".cpp", ".c"}

# Folders to always skip
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv",
    "venv", "env", "dist", "build", "target", ".idea"
}


def walk_files(repo_path: str) -> list[dict]:
    """
    Walks the cloned repo and returns all supported code files.

    Args:
        repo_path: local path of the cloned repo

    Returns:
        List of dicts:
        [
            {
                "path": "/tmp/repo/src/Main.java",
                "relative_path": "src/Main.java",
                "extension": ".java",
                "content": "public class Main { ... }"
            },
            ...
        ]
    """

    files = []

    for root, dirs, filenames in os.walk(repo_path):

        # Remove ignored dirs in-place so os.walk skips them entirely
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            full_path = os.path.join(root, filename)
            relative_path = os.path.relpath(full_path, repo_path)

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Skip empty files
                if not content.strip():
                    continue

                files.append({
                    "path": full_path,
                    "relative_path": relative_path,
                    "extension": ext,
                    "content": content
                })

            except Exception as e:
                print(f"[FileWalker] Skipping {full_path}: {e}")
                continue

    print(f"[FileWalker] Found {len(files)} files in {repo_path}")
    return files
