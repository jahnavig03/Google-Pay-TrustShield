import { NavLink, Outlet } from "react-router-dom";

import { ROLES, type Role } from "../api/client";
import { useRole } from "../role";
import { Icon } from "./ui";

export const DISCLAIMER = "Prototype simulator — synthetic data. Not affiliated with Google Pay.";

const NAV: { to: string; label: string; icon: string; role: Role }[] = [
  { to: "/pay", label: "Payment simulator", icon: "payments", role: "customer" },
  { to: "/analyst", label: "Analyst console", icon: "policy", role: "analyst" },
  { to: "/merchant", label: "Merchant check", icon: "storefront", role: "merchant" },
];

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="m8.5 12 2.5 2.5 4.5-5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export function Layout() {
  const { role, setRole } = useRole();
  return (
    <div className="app">
      {/* Disclaimer + app bar are pinned together so the disclaimer is always on screen. */}
      <div className="app-header">
        <div className="disclaimer" role="note">
          {DISCLAIMER}
        </div>
        <header className="topbar">
          <div className="brand">
            <ShieldIcon />
            <span>TrustShield</span>
            <small>simulator</small>
          </div>
          <nav className="nav" aria-label="Main">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setRole(item.role)}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              >
                <Icon name={item.icon} />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <label className="role-switcher">
            <span>Demo role</span>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
        </header>
      </div>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
