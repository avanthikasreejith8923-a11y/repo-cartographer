import React from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginView } from "./components/LoginView";
import { DashboardView } from "./components/DashboardView";

const AppContent: React.FC = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "70vh",
          gap: "1.25rem",
        }}
      >
        <div className="glass-card" style={{ padding: "2.5rem 3rem", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
          <div className="spinner" />
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", fontWeight: 500 }}>
            Authenticating with repo-cartographer...
          </p>
        </div>
      </div>
    );
  }

  return user ? <DashboardView /> : <LoginView />;
};

const HeaderNav: React.FC = () => {
  const { user, logout } = useAuth();

  return (
    <header className="navbar">
      <div className="brand">
        <div className="brand-icon">RC</div>
        <span className="brand-title">repo-cartographer</span>
        <span className="brand-badge">v1.0</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
        {user && (
          <div className="user-chip">
            <img
              src={
                user.avatar_url ||
                `https://ui-avatars.com/api/?name=${encodeURIComponent(user.login)}&background=7c5cff&color=fff`
              }
              alt={user.login}
            />
            <span style={{ fontWeight: 600 }}>@{user.login}</span>
          </div>
        )}
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          style={{
            color: "var(--text-secondary)",
            textDecoration: "none",
            fontSize: "0.88rem",
            fontWeight: 500,
            padding: "0.4rem 0.8rem",
            borderRadius: "var(--radius-pill)",
            transition: "color var(--transition-fast)",
          }}
        >
          Docs
        </a>
        {user && (
          <button
            onClick={logout}
            className="btn btn-outline btn-logout"
            aria-label="Sign Out"
            style={{ padding: "0.35rem 0.85rem", fontSize: "0.82rem" }}
          >
            Sign Out
          </button>
        )}
      </div>
    </header>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <div className="app-container">
        {/* CSS Aurora Background Color Blobs (Transforms only, pointer-events none) */}
        <div className="aurora-container" aria-hidden="true">
          <div className="aurora-blob blob-1" />
          <div className="aurora-blob blob-2" />
          <div className="aurora-blob blob-3" />
          <div className="aurora-blob blob-4" />
        </div>

        {/* Liquid Glass Header Navigation */}
        <HeaderNav />

        {/* Main View Area */}
        <main style={{ flex: 1, display: "flex", flexDirection: "column", position: "relative", zIndex: 1 }}>
          <AppContent />
        </main>

        {/* Liquid Glass Footer */}
        <footer
          style={{
            borderTop: "1px solid var(--glass-border)",
            padding: "1.5rem 2rem",
            textAlign: "center",
            fontSize: "0.85rem",
            color: "var(--text-muted)",
            background: "rgba(7, 11, 26, 0.5)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            position: "relative",
            zIndex: 1,
          }}
        >
          repo-cartographer &copy; 2026 &bull; AI Developer Productivity Platform &bull; v1.0
        </footer>
      </div>
    </AuthProvider>
  );
};

export default App;
