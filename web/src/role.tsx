import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { makeApi, type Api, type Role } from "./api/client";

const STORAGE_KEY = "trustshield.demoRole";

function readStoredRole(fallback: Role): Role {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "customer" || value === "analyst" || value === "merchant" ? value : fallback;
  } catch {
    return fallback;
  }
}

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
  api: Api;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({
  children,
  initialRole = "customer",
}: {
  children: ReactNode;
  initialRole?: Role;
}) {
  const [role, setRoleState] = useState<Role>(() => readStoredRole(initialRole));
  const setRole = useCallback((next: Role) => {
    setRoleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private mode or blocked storage: the role still applies for this session.
    }
  }, []);
  const api = useMemo(() => makeApi(role), [role]);
  const value = useMemo(() => ({ role, setRole, api }), [role, setRole, api]);
  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const value = useContext(RoleContext);
  if (!value) throw new Error("useRole must be used inside <RoleProvider>");
  return value;
}

/**
 * Each page adopts its own demo role when it opens (also on a direct URL or a reload), so a
 * stale role from another page can't make the first request fail. The role switcher can still
 * change it afterwards, e.g. to show the gateway's 403.
 */
export function usePageRole(pageRole: Role): void {
  const { setRole } = useRole();
  useEffect(() => {
    setRole(pageRole);
  }, [pageRole, setRole]);
}
