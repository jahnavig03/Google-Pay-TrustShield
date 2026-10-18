import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ANALYST_ACCESS_CODE } from "./config";

const STORAGE_KEY = "trustshield.analystSession";
const ANALYST_ID = /^[a-z0-9][a-z0-9._-]{2,39}$/i;

function readSession(): string | null {
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    return value && ANALYST_ID.test(value) ? value : null;
  } catch {
    return null;
  }
}

export type SignInResult = "ok" | "bad_id" | "bad_code";

interface SessionValue {
  analystId: string | null;
  signIn: (analystId: string, accessCode: string) => SignInResult;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

/** Analyst demo session. Lives in sessionStorage: closing the tab signs the analyst out. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [analystId, setAnalystId] = useState<string | null>(readSession);

  const signIn = useCallback((id: string, code: string): SignInResult => {
    const trimmed = id.trim();
    if (!ANALYST_ID.test(trimmed)) return "bad_id";
    if (code !== ANALYST_ACCESS_CODE) return "bad_code";
    try {
      window.sessionStorage.setItem(STORAGE_KEY, trimmed);
    } catch {
      // Storage blocked: the session still lasts until reload.
    }
    setAnalystId(trimmed);
    return "ok";
  }, []);

  const signOut = useCallback(() => {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setAnalystId(null);
  }, []);

  const value = useMemo(() => ({ analystId, signIn, signOut }), [analystId, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
