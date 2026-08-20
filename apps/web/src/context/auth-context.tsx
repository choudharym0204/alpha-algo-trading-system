"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import * as authApi from "@/lib/api/auth";
import type { CurrentUserResponse, Permission, TokenResponse } from "@/lib/api/types";
import { ApiError } from "@/lib/api/errors";
import {
  clearSession,
  getSession,
  isAccessTokenUsable,
  setSession,
  type Session,
} from "@/lib/auth/session-store";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthState {
  status: AuthStatus;
  user: CurrentUserResponse | null;
  permissions: readonly Permission[];
}

export interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  hasPermission: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function toSession(token: TokenResponse): Session {
  return {
    accessToken: token.access_token,
    refreshToken: token.refresh_token,
    accessExpiresAt: Date.now() + token.expires_in * 1000,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUserResponse | null>(null);
  const restoring = useRef(false);

  const applyUser = useCallback((current: CurrentUserResponse) => {
    setUser(current);
    setStatus("authenticated");
  }, []);

  const refresh = useCallback(async () => {
    const session = getSession();
    if (!session?.refreshToken) {
      clearSession();
      setUser(null);
      setStatus("unauthenticated");
      return;
    }
    const token = await authApi.refresh({ refresh_token: session.refreshToken });
    setSession(toSession(token));
    const current = await authApi.me(token.access_token);
    applyUser(current);
  }, [applyUser]);

  const restore = useCallback(async () => {
    if (restoring.current) return;
    restoring.current = true;
    try {
      const session = getSession();
      if (!session) {
        setStatus("unauthenticated");
        return;
      }
      if (isAccessTokenUsable(session)) {
        try {
          const current = await authApi.me(session.accessToken);
          applyUser(current);
          return;
        } catch (err) {
          if (!(err instanceof ApiError) || !err.isUnauthorized) throw err;
        }
      }
      await refresh();
    } catch {
      clearSession();
      setUser(null);
      setStatus("unauthenticated");
    } finally {
      restoring.current = false;
    }
  }, [applyUser, refresh]);

  useEffect(() => {
    void restore();
  }, [restore]);

  const login = useCallback(
    async (email: string, password: string) => {
      const token = await authApi.login({ email, password });
      setSession(toSession(token));
      const current = await authApi.me(token.access_token);
      applyUser(current);
    },
    [applyUser],
  );

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const hasPermission = useCallback(
    (permission: Permission) => {
      return user ? user.permissions.includes(permission) : false;
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      permissions: user?.permissions ?? [],
      login,
      logout,
      refresh,
      hasPermission,
    }),
    [status, user, login, logout, refresh, hasPermission],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
