import { Link } from "react-router-dom";

import { Icon } from "../components/ui";

export function CustomerHome() {
  return (
    <section className="landing" aria-labelledby="customer-title">
      <h1 id="customer-title" className="landing-title small-title">
        What would you like to do?
      </h1>
      <div className="choice-grid">
        <Link to="/customer/pay" className="choice-card">
          <Icon name="payments" className="choice-icon" />
          <span className="choice-title">Payment simulator</span>
          <span className="choice-text">
            Try a UPI payment and see whether TrustShield pauses it, and why.
          </span>
        </Link>
        <Link to="/customer/merchant" className="choice-card">
          <Icon name="storefront" className="choice-icon" />
          <span className="choice-title">Merchant check</span>
          <span className="choice-text">
            Check a “payment successful” screenshot against your ledger.
          </span>
        </Link>
      </div>
      <Link to="/" className="text-button back-link">
        <Icon name="arrow_back" />
        Back
      </Link>
    </section>
  );
}
