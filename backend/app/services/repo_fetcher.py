"""Safe in-memory GitHub repository tarball fetcher with strict file filtering."""

import hashlib
import io
import os
import tarfile
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.security import decrypt_token

# Known extensions to skip
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".dmg",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".avi",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".db", ".sqlite", ".sqlite3",
    ".csv", ".tsv", ".parquet", ".pkl", ".pickle", ".h5", ".joblib",
    ".npy", ".npz", ".feather", ".arrow",
}

LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
    "pipfile.lock",
}

EXCLUDED_DIRS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".git",
    "__pycache__",
    ".venv",
    ".next",
    ".nuxt",
    "coverage",
    ".tox",
    ".idea",
    ".vscode",
    ".turbo",
    ".cache",
}

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
}


@dataclass(frozen=True)
class FetchedFile:
    """In-memory representation of an eligible, validated codebase file."""

    path: str
    content: str
    size_bytes: int
    content_hash: str
    language: str | None


class RepoFetchError(Exception):
    """Exception raised when repository fetching fails."""

    pass


def detect_language(path: str) -> str | None:
    """Detect language based on file extension."""
    _, ext = os.path.splitext(path.lower())
    return EXTENSION_TO_LANGUAGE.get(ext)


def is_path_safe(path: str) -> bool:
    """Verify that a relative path does not escape using .. or absolute notation."""
    if os.path.isabs(path):
        return False
    parts = os.path.normpath(path).split(os.sep)
    return ".." not in parts


def should_skip_file(rel_path: str, size_bytes: int, raw_content: bytes) -> tuple[bool, str]:
    """Evaluate whether a file should be skipped based on naming, path, size, and content."""
    norm_path = rel_path.replace("\\", "/")
    filename = os.path.basename(norm_path).lower()
    _, ext = os.path.splitext(filename)

    # 1. Directory path exclusion
    path_parts = norm_path.split("/")[:-1]
    for part in path_parts:
        if part.lower() in EXCLUDED_DIRS:
            return True, f"excluded directory ({part})"

    # 2. Secret file patterns
    if (
        filename.startswith(".env")
        or filename.endswith(".pem")
        or filename.endswith(".key")
        or filename.startswith("id_rsa")
        or filename.endswith(".pfx")
        or filename.endswith(".p12")
    ):
        return True, "secret-like file"

    # 3. Lockfiles
    if filename in LOCKFILES:
        return True, "lockfile"

    # 4. Minified files and sourcemaps
    if filename.endswith(".min.js") or filename.endswith(".min.css") or filename.endswith(".map"):
        return True, "minified or map file"

    # 5. Known binary extensions
    if ext in BINARY_EXTENSIONS:
        return True, f"binary extension ({ext})"

    # 6. Size limit
    if size_bytes > settings.INDEX_MAX_FILE_BYTES:
        return True, f"file size exceeds limit ({size_bytes} > {settings.INDEX_MAX_FILE_BYTES})"

    # 7. Null-byte binary detection
    if b"\x00" in raw_content[:8000]:
        return True, "binary null byte detected"

    return False, ""


def process_tar_archive(tar_bytes: bytes) -> list[FetchedFile]:
    """Parse in-memory tar.gz archive, extract and filter code files."""
    results: list[FetchedFile] = []
    tar_stream = io.BytesIO(tar_bytes)

    try:
        with tarfile.open(fileobj=tar_stream, mode="r:*") as tar:
            members = tar.getmembers()
            for member in members:
                # Disallow symlinks, hardlinks, device nodes
                if not member.isreg():
                    continue

                raw_name = member.name
                # Strip GitHub top-level archive directory prefix (e.g. owner-repo-sha/...)
                parts = raw_name.split("/", 1)
                if len(parts) < 2:
                    continue
                clean_path = parts[1]

                if not is_path_safe(clean_path):
                    logger.warning(f"Skipping dangerous path traversal member: {raw_name}")
                    continue

                f = tar.extractfile(member)
                if f is None:
                    continue

                raw_bytes = f.read()
                size = len(raw_bytes)

                skip, reason = should_skip_file(clean_path, size, raw_bytes)
                if skip:
                    continue

                try:
                    text_content = raw_bytes.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    continue  # Skip non-UTF-8 files

                content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
                lang = detect_language(clean_path)

                results.append(
                    FetchedFile(
                        path=clean_path,
                        content=text_content,
                        size_bytes=size,
                        content_hash=content_hash,
                        language=lang,
                    )
                )
    except Exception as exc:
        raise RepoFetchError(f"Failed to read repository tarball archive: {exc}") from exc

    # Prioritize code and markdown docs, then cap at INDEX_MAX_FILES
    def file_priority(item: FetchedFile) -> int:
        if item.language in ("python", "typescript", "javascript", "go", "rust", "java", "c", "cpp"):
            return 0
        if item.language == "markdown":
            return 1
        return 2

    results.sort(key=file_priority)
    return results[: settings.INDEX_MAX_FILES]


async def fetch_repository_files(
    full_name: str,
    commit_sha: str,
    encrypted_token: str | None = None,
) -> list[FetchedFile]:
    """Stream repository tarball from GitHub API and parse members in-memory."""
    token: str | None = None
    if encrypted_token:
        try:
            token = decrypt_token(encrypted_token)
        except Exception:
            token = None

    url = f"https://api.github.com/repos/{full_name}/tarball/{commit_sha}"
    max_download_bytes = settings.INDEX_MAX_REPO_DOWNLOAD_MB * 1024 * 1024

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "repo-cartographer",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    buffer = bytearray()
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 401 and "Authorization" in headers:
                    logger.warning(
                        f"GitHub returned 401 downloading tarball for {full_name} with token. "
                        "Retrying unauthenticated for public repository..."
                    )
                    headers.pop("Authorization", None)
                    async with client.stream("GET", url, headers=headers) as unauth_resp:
                        if unauth_resp.status_code == 404:
                            raise RepoFetchError(f"Repository '{full_name}' or commit '{commit_sha}' not found on GitHub.")
                        if unauth_resp.status_code != 200:
                            raise RepoFetchError(f"GitHub returned HTTP {unauth_resp.status_code} while downloading tarball.")
                        async for chunk in unauth_resp.aiter_bytes():
                            buffer.extend(chunk)
                            if len(buffer) > max_download_bytes:
                                raise RepoFetchError(
                                    f"Repository archive exceeded max size limit of {settings.INDEX_MAX_REPO_DOWNLOAD_MB} MB."
                                )
                        logger.info(f"Downloaded {len(buffer)} bytes tarball for {full_name}@{commit_sha}. Processing in-memory...")
                        return process_tar_archive(bytes(buffer))

                if response.status_code == 404:
                    raise RepoFetchError(f"Repository '{full_name}' or commit '{commit_sha}' not found on GitHub.")
                if response.status_code != 200:
                    raise RepoFetchError(f"GitHub returned HTTP {response.status_code} while downloading tarball.")

                async for chunk in response.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > max_download_bytes:
                        raise RepoFetchError(
                            f"Repository archive exceeded max size limit of {settings.INDEX_MAX_REPO_DOWNLOAD_MB} MB."
                        )
        except httpx.HTTPError as exc:
            raise RepoFetchError(f"Network error downloading repository tarball: {exc}") from exc

    logger.info(f"Downloaded {len(buffer)} bytes tarball for {full_name}@{commit_sha}. Processing in-memory...")
    return process_tar_archive(bytes(buffer))


async def resolve_branch_head_sha(
    full_name: str,
    branch: str,
    encrypted_token: str | None = None,
) -> str:
    """Fetch the latest commit SHA for a branch from GitHub API."""
    token: str | None = None
    if encrypted_token:
        try:
            token = decrypt_token(encrypted_token)
        except Exception:
            token = None

    url = f"https://api.github.com/repos/{full_name}/commits/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "repo-cartographer",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 401 and "Authorization" in headers:
                logger.warning(
                    f"GitHub returned 401 resolving branch '{branch}' for {full_name} with token. "
                    "Retrying unauthenticated for public repository..."
                )
                headers.pop("Authorization", None)
                resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                raise RepoFetchError(f"Branch '{branch}' or repository '{full_name}' not found on GitHub.")
            if resp.status_code != 200:
                raise RepoFetchError(f"GitHub returned HTTP {resp.status_code} while resolving branch '{branch}' HEAD.")
            data = resp.json()
            sha = data.get("sha")
            if not sha:
                raise RepoFetchError(f"GitHub response for branch '{branch}' did not include commit sha.")
            return str(sha)
        except httpx.HTTPError as exc:
            raise RepoFetchError(f"Network error resolving branch '{branch}' HEAD: {exc}") from exc

