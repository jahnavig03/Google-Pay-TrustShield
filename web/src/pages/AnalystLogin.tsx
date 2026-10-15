import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ErrorNotice, Icon } from "../components/ui";
import { useSession } from "../session";

/** Demo analyst IDs for the team (docs/demo/DEMO_GUIDE.md). Suggestions only; any valid ID works. */
const TEAM_ANALYSTS = ["analyst_jahnavi", "analyst_hitesh", "analyst_ronak", "analyst_sameer"];

const ERRORS = {
  bad_id: "Enter your analyst ID (letters, numbers, dots, dashes or underscores).",
  bad_code: "That access code isn't right. Check the code shared with your team.",
} as const;

export function AnalystLogin() {
  const { analystId, signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [id, setId] = useState("analyst_demo_01");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const next = (location.state as { from?: string } | null)?.from ?? "/analyst";
  if (analystId) return <Navigate to={next} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    const result = signIn(id, code);
    if (result === "ok") navigate(next, { replace: true });
    else setError(ERRORS[result]);
  }

  return (
    <section className="landing" aria-labelledby="login-title">
      <form className="card login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-head">
          <Icon name="shield_person" className="result-icon" />
          <div>
            <h1 id="login-title" className="login-title">
              Analyst sign-in
            </h1>
            <p className="muted">Only analysts can open the case console.</p>
          </div>
        </div>
        <label>
          Analyst ID
          <input
            value={id}
            list="team-analysts"
            autoComplete="username"
            onChange={(e) => {
              setId(e.target.value);
              setError(null);
            }}
          />
        </label>
        <datalist id="team-analysts">
          {TEAM_ANALYSTS.map((a) => (
            <option key={a} value={a} />
          ))}
        </datalist>
        <label>
          Access code
          <input
            type="password"
            value={code}
            autoComplete="current-password"
            onChange={(e) => {
              setCode(e.target.value);
              setError(null);
            }}
          />
        </label>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <button type="submit" className="primary" disabled={!id.trim() || !code}>
          Sign in
        </button>
        <p className="muted small">Demo sign-in for the prototype. Synthetic data only.</p>
      </form>
      <Link to="/" className="text-button back-link">
        <Icon name="arrow_back" />
        Back
      </Link>
    </section>
  );
}

/** Route guard: the console is only reachable after analyst sign-in. */
export function RequireAnalyst({ children }: { children: ReactNode }) {
  const { analystId } = useSession();
  const location = useLocation();
  if (!analystId) {
    return <Navigate to="/analyst/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/**
 * /signout: lives outside the guarded routes, so clearing the session can't race the guard's
 * redirect to the sign-in page. Clears the session, then goes to the landing page.
 */
export function SignOut() {
  const { analystId, signOut } = useSession();
  useEffect(() => {
    signOut();
  }, [signOut]);
  return analystId ? null : <Navigate to="/" replace />;
}
