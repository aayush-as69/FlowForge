"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export default function AuthProvider({ children }) {
  const router = useRouter();
  const [state, setState] = useState({ loading: true, user: null, permissions: [], error: null });

  const refresh = useCallback(async () => {
    try {
      const me = await api("/auth/me");
      setState({ loading: false, user: me.user, permissions: me.permissions, error: null });
    } catch (e) {
      if (e.status === 401) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      else setState((s) => ({ ...s, loading: false, error: e }));
    }
  }, [router]);

  useEffect(() => { refresh(); }, [refresh]);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    router.replace("/login");
  }, [router]);

  const can = useCallback((p) => state.permissions.includes(p), [state.permissions]);
  return <AuthCtx.Provider value={{ ...state, can, logout, refresh }}>{children}</AuthCtx.Provider>;
}
