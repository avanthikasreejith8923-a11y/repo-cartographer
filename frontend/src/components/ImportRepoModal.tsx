import React, { useEffect, useState } from "react";
import { AvailableRepo } from "../types";

interface ImportRepoModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: () => void;
}

export const ImportRepoModal: React.FC<ImportRepoModalProps> = ({
  isOpen,
  onClose,
  onImportSuccess,
}) => {
  const [repos, setRepos] = useState<AvailableRepo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>("");
  const [importingRepo, setImportingRepo] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const fetchAvailable = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/repos/available?per_page=100");
        if (!res.ok) {
          throw new Error(`Failed to load GitHub repositories (${res.status})`);
        }
        const data: AvailableRepo[] = await res.json();
        setRepos(data);
      } catch (err: any) {
        setError(err.message || "Failed to load repositories");
      } finally {
        setLoading(false);
      }
    };

    fetchAvailable();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleImport = async (repo: AvailableRepo) => {
    setImportingRepo(repo.full_name);
    setError(null);
    try {
      const res = await fetch("/repos/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: repo.full_name }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Import failed with status ${res.status}`);
      }

      // Mark locally as imported
      setRepos((prev) =>
        prev.map((r) =>
          r.github_id === repo.github_id ? { ...r, is_imported: true } : r
        )
      );
      onImportSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Error importing repository");
    } finally {
      setImportingRepo(null);
    }
  };

  const filteredRepos = repos.filter(
    (r) =>
      r.full_name.toLowerCase().includes(search.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="glass-card modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: "680px",
          width: "90%",
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          padding: "2rem",
          gap: "1.25rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700 }}>Import GitHub Repository</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginTop: "0.2rem" }}>
              Select a repository from your GitHub account to cartograph and track.
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-outline"
            style={{ padding: "0.4rem 0.75rem", fontSize: "0.85rem" }}
          >
            ✕
          </button>
        </div>

        {/* Search Bar */}
        <div>
          <input
            type="text"
            className="search-input"
            placeholder="Search your repositories by name or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: "100%" }}
          />
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

        {/* Repos List */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
            paddingRight: "0.25rem",
          }}
        >
          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem", gap: "0.75rem", color: "var(--text-muted)" }}>
              <div className="spinner" />
              <span>Fetching your GitHub repositories...</span>
            </div>
          ) : filteredRepos.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              {search ? "No repositories match your search criteria." : "No GitHub repositories found."}
            </div>
          ) : (
            filteredRepos.map((repo) => (
              <div
                key={repo.github_id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "1rem 1.25rem",
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid var(--border-color)",
                  borderRadius: "var(--radius-md)",
                  gap: "1rem",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.95rem" }}>
                      {repo.full_name}
                    </span>
                    {repo.is_private ? (
                      <span className="badge badge-warning" style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem" }}>
                        Private
                      </span>
                    ) : (
                      <span className="badge badge-success" style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem" }}>
                        Public
                      </span>
                    )}
                    {repo.language && (
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        &bull; {repo.language}
                      </span>
                    )}
                  </div>
                  {repo.description && (
                    <p
                      style={{
                        color: "var(--text-secondary)",
                        fontSize: "0.82rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {repo.description}
                    </p>
                  )}
                </div>

                <div>
                  {repo.is_imported ? (
                    <span className="badge" style={{ background: "rgba(255, 255, 255, 0.08)", color: "var(--text-muted)" }}>
                      ✓ Imported
                    </span>
                  ) : (
                    <button
                      onClick={() => handleImport(repo)}
                      disabled={importingRepo === repo.full_name}
                      className="btn btn-primary"
                      style={{ padding: "0.45rem 1rem", fontSize: "0.82rem" }}
                    >
                      {importingRepo === repo.full_name ? "Importing..." : "Import"}
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
