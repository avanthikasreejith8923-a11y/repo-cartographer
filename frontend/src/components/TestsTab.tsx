import React, { useEffect, useState } from "react";
import { GeneratedTest, Repository } from "../types";

interface TestsTabProps {
  repo: Repository;
  onNavigateToIndex?: () => void;
}

export const TestsTab: React.FC<TestsTabProps> = ({ repo, onNavigateToIndex }) => {
  const isIndexed = repo.index_status === "ready";

  // File Picker State
  const [fileSearch, setFileSearch] = useState<string>("");
  const [fileList, setFileList] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [filesLoading, setFilesLoading] = useState<boolean>(false);

  // Generation State
  const [generating, setGenerating] = useState<boolean>(false);
  const [currentTest, setCurrentTest] = useState<GeneratedTest | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  // History State
  const [testHistory, setTestHistory] = useState<GeneratedTest[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Load files for picker
  useEffect(() => {
    if (!isIndexed) return;
    let isCancelled = false;

    const fetchFiles = async () => {
      setFilesLoading(true);
      try {
        const q = encodeURIComponent(fileSearch.trim());
        const res = await fetch(`/repos/${repo.id}/files?q=${q}&limit=50`);
        if (res.ok && !isCancelled) {
          const data = await res.json();
          setFileList(data.files || []);
          if (!selectedFile && data.files && data.files.length > 0) {
            setSelectedFile(data.files[0]);
          }
        }
      } catch (err) {
        console.error("Failed to load repo files:", err);
      } finally {
        if (!isCancelled) setFilesLoading(false);
      }
    };

    const debounce = setTimeout(fetchFiles, 200);
    return () => {
      isCancelled = true;
      clearTimeout(debounce);
    };
  }, [repo.id, isIndexed, fileSearch]);

  // Load test history
  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`/repos/${repo.id}/tests?limit=20`);
      if (res.ok) {
        const data: GeneratedTest[] = await res.json();
        setTestHistory(data);
      }
    } catch (err) {
      console.error("Failed to fetch test history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (isIndexed) {
      fetchHistory();
    }
  }, [repo.id, isIndexed]);

  // Generate test
  const handleGenerate = async () => {
    if (!selectedFile || generating || !isIndexed) return;

    setGenerating(true);
    setGenerateError(null);
    try {
      const res = await fetch(`/repos/${repo.id}/tests/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: selectedFile }),
      });

      if (res.status === 429) {
        setGenerateError("Rate limit exceeded. Please wait a moment before generating more tests.");
        return;
      }
      if (res.status === 409) {
        setGenerateError("Codebase has not been indexed yet. Please index before generating tests.");
        return;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setGenerateError(errData.detail || `Test generation failed (${res.status})`);
        return;
      }

      const data: GeneratedTest = await res.json();
      setCurrentTest(data);
      // Refresh history
      fetchHistory();
    } catch (err: any) {
      setGenerateError(err.message || "Failed to generate tests");
    } finally {
      setGenerating(false);
    }
  };

  // Delete test from history
  const handleDeleteTest = async (testId: string) => {
    setDeletingId(testId);
    try {
      const res = await fetch(`/repos/${repo.id}/tests/${testId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setTestHistory((prev) => prev.filter((t) => t.id !== testId));
        if (currentTest?.id === testId) {
          setCurrentTest(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete test:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleCopyCode = () => {
    if (!currentTest?.content) return;
    navigator.clipboard.writeText(currentTest.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isIndexed) {
    return (
      <div
        className="glass-card"
        style={{
          padding: "3rem 2rem",
          textAlign: "center",
          background: "rgba(99, 102, 241, 0.05)",
          borderColor: "rgba(99, 102, 241, 0.2)",
        }}
      >
        <div
          style={{
            width: "56px",
            height: "56px",
            borderRadius: "var(--radius-full)",
            background: "rgba(99, 102, 241, 0.15)",
            color: "var(--accent-primary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "1.75rem",
            margin: "0 auto 1.25rem",
          }}
        >
          🧪
        </div>
        <h3 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Codebase Not Indexed
        </h3>
        <p
          style={{
            color: "var(--text-secondary)",
            maxWidth: "520px",
            margin: "0 auto 1.5rem",
            fontSize: "0.92rem",
          }}
        >
          AI-driven unit test generation requires indexed source files. Index your codebase to start generating tests.
        </p>
        {onNavigateToIndex && (
          <button
            onClick={onNavigateToIndex}
            className="btn btn-primary"
            style={{ padding: "0.75rem 1.75rem", fontSize: "0.95rem" }}
          >
            Go to Indexing
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      {/* File Selection & Action Header Card */}
      <div className="glass-card" style={{ padding: "1.75rem" }}>
        <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "0.5rem" }}>
          🧪 AI Unit Test Generator
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginBottom: "1.25rem" }}>
          Select an indexed source file to generate focused, mock-isolated unit tests using the detected framework.
        </p>

        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end" }}>
          {/* Search/Filter Files */}
          <div style={{ flex: 1, minWidth: "260px" }}>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.4rem" }}>
              Filter Files
            </label>
            <input
              type="text"
              placeholder="Search file path (e.g. services/llm.py)..."
              value={fileSearch}
              onChange={(e) => setFileSearch(e.target.value)}
              className="search-input"
              style={{ width: "100%" }}
            />
          </div>

          {/* File Picker Dropdown */}
          <div style={{ flex: 2, minWidth: "300px" }}>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.4rem" }}>
              Select Source File {filesLoading && "(loading...)"}
            </label>
            <select
              value={selectedFile}
              onChange={(e) => setSelectedFile(e.target.value)}
              className="search-input"
              style={{ width: "100%", cursor: "pointer" }}
              disabled={filesLoading || fileList.length === 0}
            >
              {fileList.length === 0 ? (
                <option value="">No matching files found</option>
              ) : (
                fileList.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Generate Button */}
          <button
            onClick={handleGenerate}
            disabled={!selectedFile || generating}
            className="btn btn-primary"
            style={{
              padding: "0.65rem 1.4rem",
              fontSize: "0.9rem",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              minHeight: "42px",
            }}
          >
            {generating ? (
              <>
                <div className="spinner" style={{ width: "14px", height: "14px", borderWidth: "2px" }} />
                Generating Tests...
              </>
            ) : (
              "Generate Tests"
            )}
          </button>
        </div>

        {/* Error message */}
        {generateError && (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem 1rem",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid var(--danger)",
              borderRadius: "var(--radius-md)",
              color: "var(--danger)",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <span>⚠️</span>
            <span>{generateError}</span>
          </div>
        )}
      </div>

      {/* Generated Test Viewer */}
      {currentTest && (
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          {/* Disclaimer Banner */}
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(245, 158, 11, 0.1)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              borderRadius: "var(--radius-md)",
              color: "#fbbf24",
              fontSize: "0.85rem",
              fontWeight: 500,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "1.25rem",
              flexWrap: "wrap",
              gap: "0.5rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>⚠️</span>
              <span>AI-generated draft: review before use</span>
            </div>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Model: {currentTest.model}
            </span>
          </div>

          {/* Test Metadata & Actions Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "1rem",
              flexWrap: "wrap",
              gap: "0.75rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                {currentTest.path}
              </span>
              <span className="badge badge-outline" style={{ fontSize: "0.75rem" }}>
                {currentTest.framework}
              </span>

              {/* Syntax validation status */}
              {currentTest.syntax_valid === true && (
                <span className="badge badge-success" style={{ fontSize: "0.75rem" }}>
                  ✓ Syntax Valid (AST verified)
                </span>
              )}
              {currentTest.syntax_valid === false && (
                <span className="badge badge-danger" style={{ fontSize: "0.75rem" }}>
                  ✗ Syntax Error
                </span>
              )}
            </div>

            <button
              onClick={handleCopyCode}
              className="btn btn-outline"
              style={{
                padding: "0.35rem 0.85rem",
                fontSize: "0.82rem",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
              }}
            >
              {copied ? "✓ Copied!" : "📋 Copy Code"}
            </button>
          </div>

          {/* Assumptions / Notes */}
          {currentTest.notes && (
            <div
              style={{
                marginBottom: "1rem",
                padding: "0.75rem 1rem",
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-md)",
                fontSize: "0.82rem",
                color: "var(--text-secondary)",
              }}
            >
              <strong style={{ color: "var(--text-primary)" }}>Notes & Assumptions:</strong> {currentTest.notes}
            </div>
          )}

          {/* Code display block */}
          <div
            style={{
              background: "#080c14",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border-color)",
              padding: "1rem 1.25rem",
              overflowX: "auto",
              maxHeight: "550px",
              overflowY: "auto",
            }}
          >
            <pre
              style={{
                margin: 0,
                fontFamily: "var(--font-mono)",
                fontSize: "0.85rem",
                lineHeight: "1.5",
                color: "#e2e8f0",
                whiteSpace: "pre",
              }}
            >
              <code>{currentTest.content}</code>
            </pre>
          </div>
        </div>
      )}

      {/* History Card */}
      <div className="glass-card" style={{ padding: "1.75rem" }}>
        <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "1rem" }}>
          Generated Tests History ({testHistory.length})
        </h3>

        {historyLoading ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
            <div className="spinner" style={{ margin: "0 auto 0.75rem" }} />
            Loading test history...
          </div>
        ) : testHistory.length === 0 ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.88rem" }}>
            No test suites generated yet. Select a file above and click &quot;Generate Tests&quot;.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Target Path</th>
                  <th>Framework</th>
                  <th>Syntax</th>
                  <th>Created</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {testHistory.map((t) => (
                  <tr key={t.id}>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "#a5b4fc", maxWidth: "300px" }}>
                      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {t.path}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-outline" style={{ fontSize: "0.72rem" }}>
                        {t.framework}
                      </span>
                    </td>
                    <td>
                      {t.syntax_valid === true ? (
                        <span className="badge badge-success" style={{ fontSize: "0.72rem" }}>
                          Valid
                        </span>
                      ) : t.syntax_valid === false ? (
                        <span className="badge badge-danger" style={{ fontSize: "0.72rem" }}>
                          Syntax Error
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>—</span>
                      )}
                    </td>
                    <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                      {t.created_at ? new Date(t.created_at).toLocaleString() : "Recently"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                        <button
                          onClick={() => {
                            setCurrentTest(t);
                            window.scrollTo({ top: 300, behavior: "smooth" });
                          }}
                          className="btn btn-outline"
                          style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                        >
                          View
                        </button>
                        <button
                          onClick={() => handleDeleteTest(t.id)}
                          disabled={deletingId === t.id}
                          className="btn btn-outline"
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.75rem",
                            borderColor: "rgba(239, 68, 68, 0.3)",
                            color: "var(--danger)",
                          }}
                        >
                          {deletingId === t.id ? "..." : "Delete"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
