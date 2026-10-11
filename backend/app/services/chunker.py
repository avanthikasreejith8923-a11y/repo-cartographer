"""Code chunking service supporting AST chunking for Python, header chunking for Markdown,

and sliding window chunking with overlap for other languages.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

MAX_CHUNK_CHARS = 2500
WINDOW_SIZE_LINES = 60
WINDOW_OVERLAP_LINES = 10
CLASS_SPLIT_THRESHOLD_LINES = 60


@dataclass(frozen=True)
class CodeChunkItem:
    """Represents a discrete semantic chunk of a code or document file."""

    path: str
    chunk_index: int
    start_line: int
    end_line: int
    language: str
    kind: str  # function, method, class, header, block, window
    symbol: str | None
    content: str
    content_hash: str
    embed_text: str


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_embed_text(path: str, symbol: str | None, content: str) -> str:
    """Format chunk text for embedding generation."""
    if symbol:
        return f"File: {path}\nSymbol: {symbol}\n\n{content}"
    return f"File: {path}\n\n{content}"


def chunk_file(path: str, content: str, language: str) -> list[CodeChunkItem]:
    """Chunk a file into semantic or windowed chunks according to its language."""
    stripped = content.strip()
    if not stripped:
        return []

    lines = content.splitlines()
    if not lines:
        return []

    # If the file is very short (under 50 lines), keep it as a single chunk
    if len(lines) <= 50 and len(content) <= MAX_CHUNK_CHARS:
        h = compute_content_hash(content)
        return [
            CodeChunkItem(
                path=path,
                chunk_index=0,
                start_line=1,
                end_line=len(lines),
                language=language,
                kind="file",
                symbol=None,
                content=content,
                content_hash=h,
                embed_text=build_embed_text(path, None, content),
            )
        ]

    chunks: list[CodeChunkItem] = []
    if language == "python":
        chunks = _chunk_python(path, content, lines)
    elif language == "markdown":
        chunks = _chunk_markdown(path, content, lines)

    # If language specific chunker produced no chunks or failed, fall back to sliding window
    if not chunks:
        chunks = _chunk_sliding_window(path, lines, language)

    # Re-index chunks to ensure strict sequential 0..N-1 indexing
    reindexed: list[CodeChunkItem] = []
    for idx, c in enumerate(chunks):
        reindexed.append(
            CodeChunkItem(
                path=c.path,
                chunk_index=idx,
                start_line=c.start_line,
                end_line=c.end_line,
                language=c.language,
                kind=c.kind,
                symbol=c.symbol,
                content=c.content,
                content_hash=c.content_hash,
                embed_text=c.embed_text,
            )
        )
    return reindexed


def _chunk_python(path: str, content: str, lines: list[str]) -> list[CodeChunkItem]:
    """Chunk Python source code using AST parsing."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        # Fall back to sliding window on syntax errors or invalid Python code
        return _chunk_sliding_window(path, lines, "python")

    raw_chunks: list[dict] = []
    covered_lines = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or start
            node_lines = lines[start - 1 : end]
            node_text = "\n".join(node_lines).strip()
            if node_text:
                covered_lines.update(range(start, end + 1))
                raw_chunks.append({
                    "start": start,
                    "end": end,
                    "kind": "function",
                    "symbol": node.name,
                    "content": node_text,
                })
        elif isinstance(node, ast.ClassDef):
            start = node.lineno
            end = node.end_lineno or start
            class_line_count = end - start + 1

            if class_line_count > CLASS_SPLIT_THRESHOLD_LINES:
                # Split large class into methods
                methods_found = False
                for subnode in node.body:
                    if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods_found = True
                        m_start = subnode.lineno
                        m_end = subnode.end_lineno or m_start
                        m_lines = lines[m_start - 1 : m_end]
                        m_text = "\n".join(m_lines).strip()
                        if m_text:
                            covered_lines.update(range(m_start, m_end + 1))
                            raw_chunks.append({
                                "start": m_start,
                                "end": m_end,
                                "kind": "method",
                                "symbol": f"{node.name}.{subnode.name}",
                                "content": m_text,
                            })
                if not methods_found:
                    node_lines = lines[start - 1 : end]
                    node_text = "\n".join(node_lines).strip()
                    if node_text:
                        covered_lines.update(range(start, end + 1))
                        raw_chunks.append({
                            "start": start,
                            "end": end,
                            "kind": "class",
                            "symbol": node.name,
                            "content": node_text,
                        })
            else:
                node_lines = lines[start - 1 : end]
                node_text = "\n".join(node_lines).strip()
                if node_text:
                    covered_lines.update(range(start, end + 1))
                    raw_chunks.append({
                        "start": start,
                        "end": end,
                        "kind": "class",
                        "symbol": node.name,
                        "content": node_text,
                    })

    # If uncovered lines (module-level code, imports, constants) exist at top, capture them
    if raw_chunks:
        first_chunk_start = min(c["start"] for c in raw_chunks)
        if first_chunk_start > 1:
            header_lines = lines[: first_chunk_start - 1]
            header_text = "\n".join(header_lines).strip()
            if header_text:
                raw_chunks.insert(0, {
                    "start": 1,
                    "end": first_chunk_start - 1,
                    "kind": "block",
                    "symbol": "module_header",
                    "content": header_text,
                })

    # If AST produced nothing (e.g. pure script without funcs/classes), use sliding window
    if not raw_chunks:
        return _chunk_sliding_window(path, lines, "python")

    # Sort chunks by start line
    raw_chunks.sort(key=lambda x: x["start"])

    # Break any oversized chunks with sub-windowing
    result: list[CodeChunkItem] = []
    for item in raw_chunks:
        c_text = item["content"]
        if len(c_text) > MAX_CHUNK_CHARS:
            sub_lines = c_text.splitlines()
            sub_chunks = _chunk_sliding_window(
                path, sub_lines, "python", base_line=item["start"], kind=item["kind"], symbol=item["symbol"]
            )
            result.extend(sub_chunks)
        else:
            h = compute_content_hash(c_text)
            result.append(
                CodeChunkItem(
                    path=path,
                    chunk_index=len(result),
                    start_line=item["start"],
                    end_line=item["end"],
                    language="python",
                    kind=item["kind"],
                    symbol=item["symbol"],
                    content=c_text,
                    content_hash=h,
                    embed_text=build_embed_text(path, item["symbol"], c_text),
                )
            )

    return result


def _chunk_markdown(path: str, content: str, lines: list[str]) -> list[CodeChunkItem]:
    """Chunk Markdown document by header sections (#, ##, ###)."""
    header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
    sections: list[dict] = []
    current_header: str | None = None
    current_start = 1
    current_lines: list[str] = []

    for line_idx, line in enumerate(lines, start=1):
        match = header_pattern.match(line)
        if match:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append({
                        "start": current_start,
                        "end": line_idx - 1,
                        "symbol": current_header,
                        "content": text,
                    })
            current_header = match.group(0).strip()
            current_start = line_idx
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "start": current_start,
                "end": len(lines),
                "symbol": current_header,
                "content": text,
            })

    if not sections:
        return _chunk_sliding_window(path, lines, "markdown")

    result: list[CodeChunkItem] = []
    for item in sections:
        c_text = item["content"]
        if len(c_text) > MAX_CHUNK_CHARS:
            sub_lines = c_text.splitlines()
            sub_chunks = _chunk_sliding_window(
                path, sub_lines, "markdown", base_line=item["start"], kind="header", symbol=item["symbol"]
            )
            result.extend(sub_chunks)
        else:
            h = compute_content_hash(c_text)
            result.append(
                CodeChunkItem(
                    path=path,
                    chunk_index=len(result),
                    start_line=item["start"],
                    end_line=item["end"],
                    language="markdown",
                    kind="header" if item["symbol"] else "block",
                    symbol=item["symbol"],
                    content=c_text,
                    content_hash=h,
                    embed_text=build_embed_text(path, item["symbol"], c_text),
                )
            )

    return result


def _chunk_sliding_window(
    path: str,
    lines: Sequence[str],
    language: str,
    base_line: int = 1,
    kind: str = "window",
    symbol: str | None = None,
) -> list[CodeChunkItem]:
    """Sliding line window chunker with overlap."""
    total_lines = len(lines)
    if total_lines == 0:
        return []

    result: list[CodeChunkItem] = []
    step = max(1, WINDOW_SIZE_LINES - WINDOW_OVERLAP_LINES)
    start_idx = 0

    while start_idx < total_lines:
        end_idx = min(start_idx + WINDOW_SIZE_LINES, total_lines)
        window_lines = lines[start_idx:end_idx]
        window_text = "\n".join(window_lines).strip()

        if window_text:
            s_line = base_line + start_idx
            e_line = base_line + end_idx - 1
            h = compute_content_hash(window_text)
            result.append(
                CodeChunkItem(
                    path=path,
                    chunk_index=len(result),
                    start_line=s_line,
                    end_line=e_line,
                    language=language,
                    kind=kind,
                    symbol=symbol,
                    content=window_text,
                    content_hash=h,
                    embed_text=build_embed_text(path, symbol, window_text),
                )
            )

        if end_idx >= total_lines:
            break
        start_idx += step

    return result
