"""Unit tests for safe repo fetcher and file filter."""

import io
import tarfile

from app.services.repo_fetcher import (
    is_path_safe,
    process_tar_archive,
    should_skip_file,
)


def _create_tarball(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.type = tarfile.REGTYPE
            tar.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def test_file_filter_allowed_and_disallowed():
    # Allowed source code
    skip, _ = should_skip_file("app/main.py", 100, b"print('hello')")
    assert skip is False

    skip, _ = should_skip_file("frontend/src/index.tsx", 500, b"import React from 'react';")
    assert skip is False

    skip, _ = should_skip_file("README.md", 200, b"# Project")
    assert skip is False

    # Disallowed: binary extensions
    skip, reason = should_skip_file("assets/image.png", 500, b"dummy png")
    assert skip is True
    assert "binary extension" in reason

    skip, _ = should_skip_file("bin/app.exe", 1000, b"dummy exe")
    assert skip is True

    # Disallowed: lockfiles & minified
    skip, reason = should_skip_file("package-lock.json", 1000, b"{}")
    assert skip is True
    assert "lockfile" in reason

    skip, reason = should_skip_file("src/bundle.min.js", 500, b"minified")
    assert skip is True
    assert "minified" in reason

    # Disallowed: secret files
    skip, reason = should_skip_file(".env", 50, b"SECRET=123")
    assert skip is True
    assert "secret" in reason

    # Disallowed: excluded directories
    skip, reason = should_skip_file("node_modules/pkg/index.js", 100, b"")
    assert skip is True
    assert "excluded directory" in reason

    # Disallowed: oversized
    skip, reason = should_skip_file("huge.py", 300_000, b"")
    assert skip is True
    assert "exceeds limit" in reason

    # Disallowed: binary null bytes
    skip, reason = should_skip_file("custom.dat", 100, b"hello\x00world")
    assert skip is True
    assert "null byte" in reason


def test_tarball_extraction_success():
    tar_bytes = _create_tarball({
        "myrepo-abc1234/src/main.py": "print('hello')",
        "myrepo-abc1234/README.md": "# My Repo",
        "myrepo-abc1234/assets/logo.png": b"\x89PNG\r\n\x1a\n\x00\x00",  # binary, will be skipped
    })

    files = process_tar_archive(tar_bytes)
    paths = [f.path for f in files]
    assert "src/main.py" in paths
    assert "README.md" in paths
    assert "assets/logo.png" not in paths


def test_path_safety_check():
    assert is_path_safe("src/main.py") is True
    assert is_path_safe("app/core/config.py") is True

    # Traversal attempts
    assert is_path_safe("../../etc/passwd") is False
    assert is_path_safe("src/../../etc/shadow") is False
    assert is_path_safe("/absolute/path/file.py") is False
    assert is_path_safe("C:\\Windows\\system32") is False
