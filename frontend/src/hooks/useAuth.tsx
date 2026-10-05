import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, setCsrf } from "../services/api";

export type Me = { user: any; roles: string[]; permissions: string[]; csrf_token?: string };
type Ctx = {
  me: Me | null; loading: boolean; branding: any;
  login: (u: string, p: string) => Promise<any>; logout: () => Promise<void>; refresh: () => Promise<void>;
  can: (perm: string) => boolean;
};
const AuthCtx = createContext<Ctx>(null as any);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [branding, setBranding] = useState<any>({ name: "GMP-MERP", app_display_name: "GMP Material & Manufacturing ERP" });

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me");
      if (m.csrf_token) setCsrf(m.csrf_token);
      setMe(m);
    } catch { setMe(null); setCsrf(null); }
    setLoading(false);
  }, []);

  useEffect(() => {
    api("/company/branding").then(setBranding).catch(() => {});
    refresh();
    const h = () => { setMe(null); setCsrf(null); };
    window.addEventListener("merp:unauthenticated", h);
    return () => window.removeEventListener("merp:unauthenticated", h);
  }, [refresh]);

  const login = async (username: string, password: string) => {
    const r = await api("/auth/login", { method: "POST", body: { username, password } });
    setCsrf(r.csrf_token);
    await refresh();
    return r;
  };
  const logout = async () => { try { await api("/auth/logout", { method: "POST" }); } catch { /* */ } setMe(null); setCsrf(null); };
  const can = (p: string) => !!me?.permissions.includes(p);
  return <AuthCtx.Provider value={{ me, loading, branding, login, logout, refresh, can }}>{children}</AuthCtx.Provider>;
}
