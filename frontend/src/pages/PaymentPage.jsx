import { useState } from "react";
import {
  CreditCard,
  ArrowLeft,
  Lock,
  Shield,
  CheckCircle2,
  Loader,
  Database,
  Sparkles,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import { processPayment } from "../api";

export default function PaymentPage({ user, onSuccess, onBack }) {
  const [step, setStep] = useState("form"); // form | processing | success
  const [cardName, setCardName] = useState("");
  const [cardNumber, setCardNumber] = useState("");
  const [cardExpiry, setCardExpiry] = useState("");
  const [cardCvc, setCardCvc] = useState("");
  const [error, setError] = useState("");
  const [paymentResult, setPaymentResult] = useState(null);

  const formatCardNumber = (val) => {
    const digits = val.replace(/\D/g, "").slice(0, 16);
    return digits.replace(/(\d{4})(?=\d)/g, "$1 ");
  };

  const formatExpiry = (val) => {
    const digits = val.replace(/\D/g, "").slice(0, 4);
    if (digits.length >= 3) {
      return digits.slice(0, 2) + " / " + digits.slice(2);
    }
    return digits;
  };

  const getCardBrand = () => {
    const digits = cardNumber.replace(/\s/g, "");
    if (digits.startsWith("4")) return "Visa";
    if (digits.startsWith("5")) return "Mastercard";
    if (digits.startsWith("3")) return "Amex";
    if (digits.startsWith("6")) return "Discover";
    return "";
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!cardName.trim()) {
      setError("Please enter the cardholder name");
      return;
    }
    const digits = cardNumber.replace(/\s/g, "");
    if (!digits) {
      setError("Please enter a card number");
      return;
    }

    setStep("processing");

    try {
      // Simulate network delay for realism
      await new Promise((r) => setTimeout(r, 2500));

      const result = await processPayment({
        card_number: digits,
        card_expiry: cardExpiry.replace(/\s/g, ""),
        card_cvc: cardCvc,
        card_name: cardName,
        amount: 9.99,
      });

      setPaymentResult(result);
      setStep("success");
    } catch (err) {
      setStep("form");
      setError(
        err.response?.data?.detail || "Payment failed. Please try again."
      );
    }
  };

  const handleDone = () => {
    if (paymentResult) {
      onSuccess(paymentResult);
    } else {
      onBack();
    }
  };

  // Processing screen
  if (step === "processing") {
    return (
      <div className="payment-page">
        <div className="payment-processing">
          <div className="payment-processing-spinner">
            <Loader size={40} className="spin" />
          </div>
          <h2>Processing Payment</h2>
          <p>Please wait while we process your payment securely...</p>
          <div className="payment-processing-details">
            <span>Amount: $9.99</span>
            <span>Card: ****{cardNumber.replace(/\s/g, "").slice(-4)}</span>
          </div>
        </div>
      </div>
    );
  }

  // Success screen
  if (step === "success") {
    return (
      <div className="payment-page">
        <div className="payment-success">
          <div className="payment-success-icon">
            <CheckCircle2 size={48} />
          </div>
          <h2>Payment Successful!</h2>
          <p>Your payment has been processed successfully.</p>

          <div className="payment-success-receipt">
            <div className="payment-receipt-row">
              <span>Amount Paid</span>
              <span className="payment-receipt-val">$9.99</span>
            </div>
            <div className="payment-receipt-row">
              <span>Card</span>
              <span className="payment-receipt-val">
                {paymentResult?.card_brand || getCardBrand()} ****
                {paymentResult?.card_last4 ||
                  cardNumber.replace(/\s/g, "").slice(-4)}
              </span>
            </div>
            <div className="payment-receipt-row">
              <span>Credits Added</span>
              <span className="payment-receipt-val payment-receipt-credits">
                +{paymentResult?.credits_added || 50} credits
              </span>
            </div>
            <div className="payment-receipt-row">
              <span>Transaction ID</span>
              <span className="payment-receipt-val payment-receipt-txn">
                {paymentResult?.id?.slice(0, 8) || "TXN-00001"}
              </span>
            </div>
          </div>

          <button className="payment-success-btn" onClick={handleDone}>
            Go to Dashboard <ArrowRight size={14} />
          </button>
        </div>
      </div>
    );
  }

  // Payment form
  return (
    <div className="payment-page">
      <div className="payment-container">
        {/* Header */}
        <div className="payment-header">
          <button className="payment-back" onClick={onBack}>
            <ArrowLeft size={18} />
          </button>
          <div className="payment-header-brand">
            <Database size={20} />
            <span>Query Ops</span>
          </div>
        </div>

        <div className="payment-layout">
          {/* Left — Order summary */}
          <div className="payment-summary">
            <h2>Upgrade to Pro</h2>
            <div className="payment-plan-card">
              <div className="payment-plan-header">
                <Sparkles size={18} />
                <span>Pro Plan</span>
              </div>
              <div className="payment-plan-price">
                <span className="payment-plan-amount">$9.99</span>
                <span className="payment-plan-per">one-time</span>
              </div>
              <ul className="payment-plan-features">
                <li>
                  <CheckCircle2 size={14} /> 50 query credits
                </li>
                <li>
                  <CheckCircle2 size={14} /> Full chat history access
                </li>
                <li>
                  <CheckCircle2 size={14} /> All database connectors
                </li>
                <li>
                  <CheckCircle2 size={14} /> AI-powered query optimization
                </li>
                <li>
                  <CheckCircle2 size={14} /> Priority support
                </li>
              </ul>
            </div>

            <div className="payment-secure-badge">
              <Shield size={14} />
              Secured with 256-bit SSL encryption
            </div>
          </div>

          {/* Right — Card form */}
          <div className="payment-form-wrapper">
            <h3>Payment Details</h3>

            {error && (
              <div className="payment-error">
                <AlertCircle size={14} />
                {error}
              </div>
            )}

            <form className="payment-form" onSubmit={handleSubmit}>
              <div className="payment-field">
                <label>Cardholder Name</label>
                <input
                  type="text"
                  value={cardName}
                  onChange={(e) => setCardName(e.target.value)}
                  placeholder="John Doe"
                />
              </div>

              <div className="payment-field">
                <label>Card Number</label>
                <div className="payment-card-input">
                  <CreditCard size={16} className="payment-field-icon" />
                  <input
                    type="text"
                    value={cardNumber}
                    onChange={(e) =>
                      setCardNumber(formatCardNumber(e.target.value))
                    }
                    placeholder="4242 4242 4242 4242"
                    maxLength={19}
                  />
                  {getCardBrand() && (
                    <span className="payment-card-brand">{getCardBrand()}</span>
                  )}
                </div>
              </div>

              <div className="payment-field-row">
                <div className="payment-field">
                  <label>Expiry Date</label>
                  <input
                    type="text"
                    value={cardExpiry}
                    onChange={(e) =>
                      setCardExpiry(formatExpiry(e.target.value))
                    }
                    placeholder="MM / YY"
                    maxLength={7}
                  />
                </div>
                <div className="payment-field">
                  <label>CVC</label>
                  <div className="payment-cvc-input">
                    <input
                      type="text"
                      value={cardCvc}
                      onChange={(e) =>
                        setCardCvc(e.target.value.replace(/\D/g, "").slice(0, 4))
                      }
                      placeholder="123"
                      maxLength={4}
                    />
                    <Lock size={14} className="payment-cvc-icon" />
                  </div>
                </div>
              </div>

              <button type="submit" className="payment-submit">
                <Lock size={14} />
                Pay $9.99
              </button>

              <div className="payment-footer-badges">
                <span>
                  <Lock size={10} /> Secure
                </span>
                <span>
                  <Shield size={10} /> Encrypted
                </span>
                <span>
                  <CreditCard size={10} /> PCI Compliant
                </span>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
