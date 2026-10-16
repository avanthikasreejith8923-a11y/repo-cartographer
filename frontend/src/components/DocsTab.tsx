import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { DocResponse, Repository, SourceCitation } from "../types";

interface DocsTabProps {
  repo: Repository;
  onNavigateToIndex?: () => void;
}

type DocType = "architecture" | "readme";

export const DocsTab: React.FC<DocsTabProps> = ({ repo, onNavigateToIndex }) => {
  const [selectedDocType, setSelectedDocType] = useState<DocType>("architecture");
  const [doc, setDoc] = useState<DocResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [generating, setGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const isIndexed = repo.index_status === "ready";

  const fetchDoc = async (type: DocType) => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/repos/${repo.id}/docs/${type}`);
      if (res.ok) {
        const data: DocResponse = await res.json();
        setDoc(data);
        if (data.status === "pending" || data.status === "generating") {
          setGenerating(true);
        } else {
          setGenerating(false);
        }
      }
    } catch (err: any) {
      setError(err.message || "Failed to load documentation");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isIndexed) {
      fetchDoc(selectedDocType);
    }
  }, [repo.id, selectedDocType, isIndexed]);

  // Polling when doc generation is pending or generating
  useEffect(() => {
    let timer: any = null;
    if (generating) {
      timer = setInterval(async () => {
        try {
          const res = await fetch(`/repos/${repo.id}/docs/${selectedDocType}`);
          if (res.ok) {
            const data: DocResponse = await res.json();
            setDoc(data);
            if (data.status === "ready" || data.status === "failed") {
              setGenerating(false);
              if (data.status === "failed") {
                setError(data.error || "Documentation generation failed.");
              }
            }
          }
        } catch (err) {
          console.error("Polling doc status failed:", err);
        }
      }, 2500);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [generating, repo.id, selectedDocType]);

  const handleGenerate = async () => {
    if (generating || !isIndexed) return;
    setGenerating(true);
    setError(null);

    try {
      const res = await fetch(`/repos/${repo.id}/docs/${selectedDocType}/generate`, {
        method: "POST",
      });
      if (res.status === 409) {
        throw new Error("Documentation generation is already in progress.");
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to trigger documentation generation");
      }
      const data: DocResponse = await res.json();
      setDoc(data);
    } catch (err: any) {
      setError(err.message || "Generation error");
      setGenerating(false);
    }
  };

  const handleCopyMarkdown = () => {
    if (!doc?.content_markdown) return;
    navigator.clipboard.writeText(doc.content_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isIndexed) {
    return (
      <div className="glass-card" style={{ padding: "2.5rem", textAlign: "center", maxWidth: "600px", margin: "2rem auto" }}>
        <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>📖</div>
        <h3 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>Repository Not Indexed</h3>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem", fontSize: "0.95rem" }}>
          To synthesize architecture documentation and README drafts grounded in this repository's codebase, indexing must be completed first.
        </p>
        {onNavigateToIndex && (
          <button className="btn btn-primary" onClick={onNavigateToIndex}>
            Go to Search & Indexing Tab
          </button>
        )}
      </div>
    );
  }

  const isReady = doc?.status === "ready" && doc.content_markdown;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Top Toolbar */}
      <div className="glass-card" style={{ padding: "1.25rem", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        {/* Document Type Selector */}
        <div style={{ display: "flex", background: "rgba(0, 0, 0, 0.3)", borderRadius: "var(--radius-md)", padding: "0.25rem", border: "1px solid var(--border-color)" }}>
          <button
            type="button"
            onClick={() => setSelectedDocType("architecture")}
            disabled={generating}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "var(--radius-sm)",
              border: "none",
              background: selectedDocType === "architecture" ? "var(--accent-primary)" : "transparent",
              color: selectedDocType === "architecture" ? "#ffffff" : "var(--text-secondary)",
              fontWeight: 600,
              fontSize: "0.9rem",
              cursor: "pointer",
              transition: "all var(--transition-fast)",
            }}
          >
            🏛️ Architecture Overview
          </button>
          <button
            type="button"
            onClick={() => setSelectedDocType("readme")}
            disabled={generating}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "var(--radius-sm)",
              border: "none",
              background: selectedDocType === "readme" ? "var(--accent-primary)" : "transparent",
              color: selectedDocType === "readme" ? "#ffffff" : "var(--text-secondary)",
              fontWeight: 600,
              fontSize: "0.9rem",
              cursor: "pointer",
              transition: "all var(--transition-fast)",
            }}
          >
            📄 README Draft
          </button>
        </div>

        {/* Action Buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {isReady && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCopyMarkdown}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
            >
              {copied ? "✓ Copied!" : "📋 Copy Markdown"}
            </button>
          )}

          <button
            type="button"
            className="btn btn-primary"
            onClick={handleGenerate}
            disabled={generating || loading}
            style={{ minWidth: "160px" }}
          >
            {generating ? (
              <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span className="spinner" style={{ width: "14px", height: "14px", borderWidth: "2px" }} />
                Generating...
              </span>
            ) : isReady ? (
              `↻ Regenerate ${selectedDocType === "architecture" ? "Architecture" : "README"}`
            ) : (
              `⚡ Generate ${selectedDocType === "architecture" ? "Architecture" : "README"}`
            )}
          </button>
        </div>
      </div>

      {/* Generating Progress Banner */}
      {generating && (
        <div className="glass-card" style={{ padding: "1.5rem", borderLeft: "4px solid var(--accent-primary)", display: "flex", alignItems: "center", gap: "1rem" }}>
          <div className="spinner" style={{ width: "24px", height: "24px", borderWidth: "3px" }} />
          <div>
            <h4 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
              Generating {selectedDocType === "architecture" ? "Architecture" : "README"} Document
            </h4>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              Collecting file hierarchy, key manifest dependencies, entrypoints, and querying Gemini for grounding.
              This typically takes 15-30 seconds.
            </p>
          </div>
        </div>
      )}

      {/* Stale Warning Banner */}
      {doc?.is_stale && isReady && (
        <div style={{ padding: "0.85rem 1.25rem", borderRadius: "var(--radius-md)", background: "var(--warning-bg)", border: "1px solid var(--warning)", color: "var(--warning)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
          <span style={{ fontSize: "0.9rem" }}>
            ⚠️ This documentation was generated for commit <code style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{doc.indexed_commit_sha?.slice(0, 7) || "earlier"}</code> and may be out of sync with the latest indexed commit.
          </span>
          <button
            onClick={handleGenerate}
            className="btn btn-primary"
            style={{ padding: "0.3rem 0.75rem", fontSize: "0.8rem", whiteSpace: "nowrap" }}
          >
            Regenerate Now
          </button>
        </div>
      )}

      {/* Error Banner */}
      {error && !generating && (
        <div style={{ padding: "1rem", borderRadius: "var(--radius-md)", background: "var(--danger-bg)", border: "1px solid var(--danger)", color: "var(--danger)", fontSize: "0.9rem" }}>
          ⚠️ {error}
        </div>
      )}

      {/* Empty State */}
      {!isReady && !generating && !loading && (
        <div className="glass-card" style={{ padding: "3rem 2rem", textAlign: "center" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>
            {selectedDocType === "architecture" ? "🏛️" : "📄"}
          </div>
          <h3 style={{ fontSize: "1.2rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            No {selectedDocType === "architecture" ? "Architecture Overview" : "README Draft"} Generated Yet
          </h3>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", maxWidth: "500px", margin: "0 auto 1.5rem" }}>
            Click Generate to analyze the repository structure, code entrypoints, and dependencies, and produce an automated, cited {selectedDocType} specification.
          </p>
          <button className="btn btn-primary" onClick={handleGenerate}>
            Generate {selectedDocType === "architecture" ? "Architecture" : "README"}
          </button>
        </div>
      )}

      {/* Rendered Document */}
      {isReady && !generating && (
        <div className="glass-card" style={{ padding: "2.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "1rem", marginBottom: "2rem" }}>
            <div>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Model: {doc.model || "gemini-3.5-flash-lite"} • Generated: {doc.generated_at ? new Date(doc.generated_at).toLocaleString() : "Recently"}
              </span>
            </div>
            <span style={{ padding: "0.2rem 0.6rem", borderRadius: "var(--radius-full)", background: "var(--success-bg)", color: "var(--success)", fontSize: "0.75rem", fontWeight: 600 }}>
              Status: Ready
            </span>
          </div>

          <div className="markdown-content" style={{ lineHeight: "1.8", color: "var(--text-primary)" }}>
            <ReactMarkdown>{doc.content_markdown || ""}</ReactMarkdown>
          </div>

          {/* Citations section if present */}
          {doc.citations && doc.citations.length > 0 && (
            <div style={{ marginTop: "3rem", borderTop: "1px solid var(--border-color)", paddingTop: "1.5rem" }}>
              <h4 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "1rem" }}>
                Grounding Sources & Permalinks ({doc.citations.length})
              </h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "0.75rem" }}>
                {doc.citations.map((c: SourceCitation) => (
                  <div
                    key={c.marker}
                    style={{
                      padding: "0.75rem",
                      borderRadius: "var(--radius-md)",
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--border-color)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <span style={{ background: "var(--accent-primary)", color: "#fff", padding: "0.1rem 0.4rem", borderRadius: "var(--radius-sm)", fontSize: "0.75rem", fontWeight: 700, marginRight: "0.5rem" }}>
                        {c.marker}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                        {c.path.split("/").pop()}:{c.start_line}
                      </span>
                    </div>
                    <a
                      href={c.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontSize: "0.75rem", color: "var(--accent-primary)", textDecoration: "none" }}
                    >
                      GitHub ↗
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
