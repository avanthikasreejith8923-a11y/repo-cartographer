import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { User } from "../types";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
  login: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState<boolean>(false);
  const hadUserRef = useRef<boolean>(false);

  const clearSessionExpired = useCallback(() => {
    setSessionExpired(false);
  }, []);

  const fetchCurrentUser = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch("/auth/me", {
        credentials: "include",
        headers: {
          Accept: "application/json",
        },
      });

      if (response.ok) {
        const data: User = await response.json();
        setUser(data);
        hadUserRef.current = true;
        setSessionExpired(false);
      } else if (response.status === 401) {
        if (hadUserRef.current) {
          setSessionExpired(true);
        }
        setUser(null);
      } else {
        setError(`Failed to fetch user state (${response.status})`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Network error checking session";
      setError(message);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  // Global fetch interceptor to catch any 401 across the application
  useEffect(() => {
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      if (response.status === 401) {
        const rawUrl = typeof args[0] === "string" ? args[0] : (args[0] && (args[0] as Request).url) || "";
        // Only set sessionExpired if user was previously authenticated or request is an app endpoint
        if (!rawUrl.includes("/auth/me") || hadUserRef.current) {
          setUser(null);
          setSessionExpired(true);
        }
      }
      return response;
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  const login = () => {
    // Initiate GitHub OAuth flow via backend redirect
    setSessionExpired(false);
    window.location.href = "/auth/github/login";
  };

  const logout = async () => {
    try {
      setLoading(true);
      setSessionExpired(false);
      hadUserRef.current = false;
      await fetch("/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      setUser(null);
      // Clean query params if any
      if (window.location.search) {
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    } catch (err: unknown) {
      console.error("Logout error:", err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        sessionExpired,
        clearSessionExpired,
        login,
        logout,
        refreshUser: fetchCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
