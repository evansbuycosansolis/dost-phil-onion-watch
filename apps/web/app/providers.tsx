"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { currentUser } from "@phil-onion-watch/api-client";
import type { SessionUser } from "@phil-onion-watch/types";

type AuthContextValue = {
  token?: string;
  user?: SessionUser;
  setToken: (token?: string) => void;
  refreshUser: () => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function normalizeUser(raw: Record<string, unknown>): SessionUser {
  return {
    id: Number(raw.id),
    email: String(raw.email),
    fullName: String(raw.full_name),
    roles: (raw.roles as SessionUser["roles"]) ?? [],
    municipalityId: raw.municipality_id ? Number(raw.municipality_id) : undefined,
    authSource: raw.auth_source ? String(raw.auth_source) : undefined,
    mfaVerified: raw.mfa_verified === undefined ? undefined : Boolean(raw.mfa_verified),
  };
}

function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | undefined>(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    return window.localStorage.getItem("pow_token") ?? undefined;
  });
  const [user, setUser] = useState<SessionUser | undefined>(undefined);

  const refreshUser = useCallback(async () => {
    if (!token) {
      setUser(undefined);
      return;
    }
    try {
      const me = await currentUser(token);
      setUser(normalizeUser((me.user ?? {}) as Record<string, unknown>));
    } catch {
      setUser(undefined);
    }
  }, [token]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const setToken = (nextToken?: string) => {
    if (!nextToken) {
      window.localStorage.removeItem("pow_token");
      setTokenState(undefined);
      setUser(undefined);
      return;
    }
    window.localStorage.setItem("pow_token", nextToken);
    setTokenState(nextToken);
  };

  const logout = useCallback(() => setToken(undefined), []);

  const value = useMemo(() => ({ token, user, setToken, refreshUser, logout }), [logout, refreshUser, token, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

const queryClient = new QueryClient();

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within Providers");
  }
  return context;
}
