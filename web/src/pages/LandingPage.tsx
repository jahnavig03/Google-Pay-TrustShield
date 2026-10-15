import { Link } from "react-router-dom";

import { ShieldMark } from "../components/Brand";
import { Icon } from "../components/ui";

export function LandingPage() {
  return (
    <section className="landing" aria-labelledby="landing-title">
      <div className="landing-mark">
        <ShieldMark size={64} />
      </div>
      <h1 id="landing-title" className="landing-title">
        TrustShield
      </h1>
      <p className="landing-tagline">Stops payments made under pressure, before they go through.</p>

      <div className="choice-grid">
        <Link to="/customer" className="choice-card">
          <Icon name="person" className="choice-icon" />
          <span className="choice-title">Continue as customer</span>
          <span className="choice-text">Check a payment or a payment screenshot.</span>
        </Link>
        <Link to="/analyst/login" className="choice-card">
          <Icon name="shield_person" className="choice-icon" />
          <span className="choice-title">Sign in as analyst</span>
          <span className="choice-text">Review flagged cases and approve actions.</span>
        </Link>
      </div>
    </section>
  );
}
