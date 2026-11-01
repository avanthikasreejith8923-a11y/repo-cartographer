import React, { useEffect, useState } from "react";
import { Repository } from "../types";
import { ImportRepoModal } from "./ImportRepoModal";

interface RepoListViewProps {
  onSelectRepo: (repo: Repository) => void;
}

export const RepoListView: React.FC<RepoListViewProps> = ({ onSelectRepo }) => {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [resyncingId, setResyncingId] = useState<string | null>(null);

  const fetchRepos = async (showLoading: boolean = false) => {
    if (showLoading) setLoading(true);
    try {
      const res = await fetch("/repos");
      if (res.ok) {
        const data: Repository[] = await res.json();
        setRepos(data);
      } else {
        throw new Error(`Failed to load repositories (${res.status})`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load repositories");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos(true);
  }, []);

  const hasActiveSync = repos.some(
    (r) => r.status === "pending" || r.status === "syncing"
  );

  // Poll while any repo is pending or syncing
  useEffect(() => {
    let interval: any = null;
    if (hasActiveSync) {
      interval = setInterval(() => {
        fetchRepos(false);
      }, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [hasActiveSync]);

  const handleResync = async (e: React.MouseEvent, repoId: string) => {
    e.stopPropagation();
    if (resyncingId) return;
    setResyncingId(repoId);
    try {
      const res = await fetch(`/repos/${repoId}/sync`, { method: "POST" });
      if (res.ok || res.status === 409) {
        // Immediate status update locally
        setRepos((prev) =>
          prev.map((r) => (r.id === repoId ? { ...r, status: "pending", sync_error: null } : r))
        );
      }
    } catch (err) {
      console.error("Failed to trigger re-sync:", err);
    } finally {
      setResyncingId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, repo: Repository) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to remove '${repo.full_name}' and its synced data?`)) {
      return;
    }
    try {
      const res = await fetch(`/repos/${repo.id}`, { method: "DELETE" });
      if (res.ok) {
        setRepos((prev) => prev.filter((r) => r.id !== repo.id));
      }
    } catch (err) {
      console.error("Failed to delete repository:", err);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header with Import Button */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>Tracked Repositories</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginTop: "0.2rem" }}>
            Synchronize GitHub commits, pull requests, and issues with local cartography.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          disabled={hasActiveSync}
          className="btn btn-primary"
          style={{
            padding: "0.6rem 1.25rem",
            fontSize: "0.88rem",
            opacity: hasActiveSync ? 0.6 : 1,
            cursor: hasActiveSync ? "not-allowed" : "pointer",
          }}
          title={hasActiveSync ? "Sync in progress. Please wait until sync finishes to import." : undefined}
        >
          {hasActiveSync ? "Sync in progress..." : "+ Import Repository"}
        </button>
      </div>

      {error && (
        <div
          style={{
            padding: "0.75rem 1rem",
            background: "var(--danger-bg)",
            border: "1px solid var(--danger)",
            borderRadius: "var(--radius-md)",
            color: "var(--danger)",
            fontSize: "0.85rem",
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: "4rem", textAlign: "center", color: "var(--text-muted)" }}>
          <div className="spinner" style={{ margin: "0 auto 1rem" }} />
          Loading tracked repositories...
        </div>
      ) : repos.length === 0 ? (
        <div
          className="glass-card"
          style={{
            padding: "3.5rem 2rem",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "1rem",
          }}
        >
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "50%",
              background: "rgba(99, 102, 241, 0.1)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--accent-primary)",
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 6h10" />
              <path d="M6 10h10" />
            </svg>
          </div>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 600 }}>No repositories imported yet</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", maxWidth: "420px", margin: "0.4rem auto 0" }}>
              Import a repository from your GitHub account to begin asynchronous ingestion of commits, pull requests, and issues.
            </p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            disabled={hasActiveSync}
            className="btn btn-primary"
            style={{ marginTop: "0.5rem", opacity: hasActiveSync ? 0.6 : 1 }}
          >
            {hasActiveSync ? "Sync in progress..." : "Import your first repository"}
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "1.25rem" }}>
          {repos.map((repo) => (
            <div
              key={repo.id}
              onClick={() => onSelectRepo(repo)}
              className="glass-card repo-card"
              style={{
                padding: "1.5rem",
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: "1.25rem",
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", marginBottom: "0.5rem" }}>
                  <h3
                    style={{
                      fontSize: "1.05rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {repo.full_name}
                  </h3>
                  <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                    {repo.index_status && repo.index_status !== "none" && (
                      <span
                        className={`badge badge-${
                          repo.index_status === "ready"
                            ? "success"
                            : (repo.chunk_count && repo.chunk_count > 0 && repo.index_status === "failed")
                            ? "warning"
                            : repo.index_status === "failed"
                            ? "danger"
                            : "warning"
                        }`}
                        style={{ fontSize: "0.72rem", flexShrink: 0 }}
                      >
                        {repo.index_status === "ready"
                          ? "Indexed"
                          : (repo.chunk_count && repo.chunk_count > 0 && repo.index_status === "failed")
                          ? "Partial Index"
                          : repo.index_status === "indexing"
                          ? "Indexing..."
                          : "Index Failed"}
                      </span>
                    )}
                    <span
                      className={`badge badge-${
                        repo.status === "ready"
                          ? "success"
                          : repo.status === "failed"
                          ? "danger"
                          : "warning"
                      }`}
                      style={{ fontSize: "0.72rem", flexShrink: 0 }}
                    >
                      <span
                        className={`badge-dot ${
                          repo.status === "syncing" || repo.status === "pending" ? "pulse-dot" : ""
                        }`}
                      />
                      {repo.status}
                    </span>
                  </div>
                </div>

                <p
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: "0.85rem",
                    lineHeight: 1.4,
                    height: "2.8rem",
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {repo.description || "No description provided."}
                </p>
                {repo.status === "failed" && repo.sync_error && (
                  <p style={{ color: "var(--danger)", fontSize: "0.8rem", marginTop: "0.4rem", lineHeight: 1.3 }}>
                    ⚠️ {repo.sync_error}
                  </p>
                )}
              </div>

              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.78rem",
                    color: "var(--text-muted)",
                    borderTop: "1px solid var(--border-color)",
                    paddingTop: "0.75rem",
                    marginBottom: "0.75rem",
                  }}
                >
                  <span>Branch: <strong style={{ color: "var(--text-secondary)" }}>{repo.default_branch}</strong></span>
                  {repo.language && (
                    <span>Language: <strong style={{ color: "var(--text-secondary)" }}>{repo.language}</strong></span>
                  )}
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                    {repo.last_synced_at
                      ? `Synced ${new Date(repo.last_synced_at).toLocaleDateString()}`
                      : "Not synced yet"}
                  </span>

                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      onClick={(e) => handleResync(e, repo.id)}
                      disabled={repo.status === "syncing" || repo.status === "pending" || resyncingId !== null}
                      className="btn btn-outline"
                      style={{ padding: "0.3rem 0.65rem", fontSize: "0.75rem" }}
                      title="Trigger Re-sync"
                    >
                      {repo.status === "syncing" || repo.status === "pending"
                        ? "Syncing..."
                        : resyncingId === repo.id
                        ? "Starting..."
                        : "Re-sync"}
                    </button>
                    <button
                      onClick={(e) => handleDelete(e, repo)}
                      className="btn btn-outline"
                      style={{ padding: "0.3rem 0.65rem", fontSize: "0.75rem", color: "var(--danger)" }}
                      title="Remove Repository"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Import Modal */}
      <ImportRepoModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onImportSuccess={() => fetchRepos(false)}
        isSyncInProgress={hasActiveSync}
      />
    </div>
  );
};
