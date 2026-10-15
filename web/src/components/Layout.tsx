import type { ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { useSession } from "../session";
import { ShieldMark } from "./Brand";
import { Icon } from "./ui";

export const DISCLAIMER = "Prototype simulator — synthetic data. Not affiliated with Google Pay.";

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const CUSTOMER_NAV: NavItem[] = [
  { to: "/customer/pay", label: "Payment simulator", icon: "payments" },
  { to: "/customer/merchant", label: "Merchant check", icon: "storefront" },
];

const ANALYST_NAV: NavItem[] = [{ to: "/analyst", label: "Analyst console", icon: "policy" }];

/** Disclaimer + app bar (pinned together, so the disclaimer is always on screen) + page. */
function Shell({ nav = [], actions }: { nav?: NavItem[]; actions?: ReactNode }) {
  return (
    <div className="app">
      <div className="app-header">
        <div className="disclaimer" role="note">
          {DISCLAIMER}
        </div>
        <header className="topbar">
          <Link to="/" className="brand" aria-label="TrustShield home">
            <ShieldMark />
            <span>TrustShield</span>
          </Link>
          {nav.length > 0 && (
            <nav className={nav.length === 1 ? "nav nav-single" : "nav"} aria-label="Main">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          )}
          {actions && <div className="topbar-actions">{actions}</div>}
        </header>
      </div>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

/** Landing, the customer's choice screen and the analyst sign-in. */
export function BareLayout() {
  return <Shell />;
}

export function CustomerLayout() {
  return (
    <Shell
      nav={CUSTOMER_NAV}
      actions={
        <Link to="/" className="text-button">
          <Icon name="logout" />
          Exit
        </Link>
      }
    />
  );
}

export function AnalystLayout() {
  const { analystId } = useSession();
  return (
    <Shell
      nav={ANALYST_NAV}
      actions={
        <>
          <span className="user-chip" title="Signed-in analyst">
            <Icon name="badge" />
            {analystId}
          </span>
          <Link to="/signout" replace className="text-button">
            <Icon name="logout" />
            Sign out
          </Link>
        </>
      }
    />
  );
}
