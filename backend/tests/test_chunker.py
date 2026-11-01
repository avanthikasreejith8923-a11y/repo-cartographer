"""Unit tests for code chunker service."""

from app.services.chunker import (
    CLASS_SPLIT_THRESHOLD_LINES,
    build_embed_text,
    chunk_file,
    compute_content_hash,
)


def test_empty_content_returns_empty():
    assert chunk_file("test.py", "", "python") == []
    assert chunk_file("test.py", "   \n\n  ", "python") == []


def test_short_file_returns_single_file_chunk():
    content = "x = 1\ny = 2\nprint(x + y)"
    chunks = chunk_file("app/main.py", content, "python")
    assert len(chunks) == 1
    assert chunks[0].kind == "file"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[0].content == content
    assert chunks[0].chunk_index == 0


def test_python_ast_functions_and_classes():
    # Long enough Python code to trigger AST chunking (>50 lines)
    code_lines = [
        '"""Module docstring."""',
        "import os",
        "import sys",
        "",
        "GLOBAL_CONST = 42",
        "",
    ]
    # Add dummy padding lines
    for i in range(50):
        code_lines.append(f"# comment line {i}")

    code_lines.extend([
        "def calculate_sum(a: int, b: int) -> int:",
        '    """Sum two numbers."""',
        "    return a + b",
        "",
        "class Calculator:",
        "    def multiply(self, x: int, y: int) -> int:",
        "        return x * y",
    ])
    content = "\n".join(code_lines)

    chunks = chunk_file("calc.py", content, "python")
    assert len(chunks) >= 2

    # Check function chunk
    func_chunk = next((c for c in chunks if c.symbol == "calculate_sum"), None)
    assert func_chunk is not None
    assert func_chunk.kind == "function"
    assert "def calculate_sum" in func_chunk.content

    # Check class chunk
    class_chunk = next((c for c in chunks if c.symbol == "Calculator"), None)
    assert class_chunk is not None
    assert class_chunk.kind == "class"
    assert "class Calculator:" in class_chunk.content


def test_python_ast_split_large_class():
    code_lines = ["class LargeService:"]
    # Build large class with multiple methods exceeding CLASS_SPLIT_THRESHOLD_LINES
    for i in range(CLASS_SPLIT_THRESHOLD_LINES + 10):
        code_lines.append(f"    # line padding {i}")

    code_lines.extend([
        "    def method_one(self):",
        "        return 1",
        "",
        "    def method_two(self):",
        "        return 2",
    ])
    content = "\n".join(code_lines)

    chunks = chunk_file("service.py", content, "python")
    symbols = [c.symbol for c in chunks]
    assert "LargeService.method_one" in symbols
    assert "LargeService.method_two" in symbols


def test_python_syntax_error_fallback_to_sliding_window():
    # Syntax error with many lines
    lines = ["def broken_func("] + [f"    line_{i} = {i}" for i in range(70)]
    content = "\n".join(lines)
    chunks = chunk_file("broken.py", content, "python")
    assert len(chunks) >= 2
    assert all(c.kind == "window" for c in chunks)


def test_markdown_chunking_by_headers():
    lines = [
        "# Project Overview",
        "Welcome to the project documentation.",
        "Here is some overview text.",
    ]
    for i in range(60):
        lines.append(f"More overview detail {i}")

    lines.extend([
        "## Installation",
        "Run pip install -r requirements.txt",
        "Ensure Python 3.11 is installed.",
        "## Usage",
        "Run python -m app.main",
    ])
    content = "\n".join(lines)

    chunks = chunk_file("README.md", content, "markdown")
    assert len(chunks) >= 3
    symbols = [c.symbol for c in chunks if c.symbol]
    assert any("# Project Overview" in s for s in symbols)
    assert any("## Installation" in s for s in symbols)
    assert any("## Usage" in s for s in symbols)


def test_sliding_window_chunking_for_other_languages():
    lines = [f"const x{i} = {i};" for i in range(130)]
    content = "\n".join(lines)
    chunks = chunk_file("script.ts", content, "typescript")
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 60
    # Overlap of 10 lines: next chunk starts at 51
    assert chunks[1].start_line == 51
    assert chunks[0].kind == "window"
    assert chunks[0].language == "typescript"


def test_content_hash_and_embed_text():
    content = "def hello():\n    return 'world'"
    h = compute_content_hash(content)
    assert len(h) == 64
    assert h == compute_content_hash(content)

    embed_with_sym = build_embed_text("path/test.py", "hello", content)
    assert "File: path/test.py" in embed_with_sym
    assert "Symbol: hello" in embed_with_sym

    embed_without_sym = build_embed_text("path/test.py", None, content)
    assert "File: path/test.py" in embed_without_sym
    assert "Symbol:" not in embed_without_sym


def test_oversized_chunk_splitting_across_file_types():
    from app.services.chunker import MAX_CHUNK_CHARS

    # 1. Plain text with a massive single line (> 2 * MAX_CHUNK_CHARS)
    massive_line = "A" * (MAX_CHUNK_CHARS * 2 + 500)
    chunks_txt = chunk_file("data.txt", massive_line, "plaintext")
    assert len(chunks_txt) >= 3
    for c in chunks_txt:
        assert len(c.content) <= MAX_CHUNK_CHARS

    # 2. Markdown with huge text under a single header
    huge_md = "# Title\n" + ("B" * (MAX_CHUNK_CHARS + 200)) + "\n## Next\nNormal"
    chunks_md = chunk_file("doc.md", huge_md, "markdown")
    for c in chunks_md:
        assert len(c.content) <= MAX_CHUNK_CHARS

    # 3. Python code with a huge function
    huge_func = "def huge():\n" + ("    x = 1\n" * 400)
    chunks_py = chunk_file("huge.py", huge_func, "python")
    for c in chunks_py:
        assert len(c.content) <= MAX_CHUNK_CHARS

