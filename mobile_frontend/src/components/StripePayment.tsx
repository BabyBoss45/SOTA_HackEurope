"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  ExpressCheckoutElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!
);

interface StripePaymentProps {
  jobId: number;
  amount: number;
  agentAddress: string;
  boardJobId?: string;
  onSuccess: () => void;
  onError: (error: string) => void;
}

/* ── Inner checkout form (rendered inside <Elements>) ── */
function CheckoutForm({
  amount,
  onSuccess,
  onError,
}: {
  amount: number;
  onSuccess: () => void;
  onError: (error: string) => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [paymentStatus, setPaymentStatus] = useState<
    "idle" | "processing" | "success" | "error"
  >("idle");

  const confirmPayment = useCallback(async () => {
    if (!stripe || !elements) return;

    setPaymentStatus("processing");

    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: "if_required",
    });

    if (error) {
      setPaymentStatus("error");
      onError(error.message || "Payment failed");
    } else {
      setPaymentStatus("success");
      onSuccess();
    }
  }, [stripe, elements, onSuccess, onError]);

  const handleExpressCheckout = useCallback(
    async (_event: { expressPaymentType: string }) => {
      await confirmPayment();
    },
    [confirmPayment]
  );

  if (paymentStatus === "success") {
    return (
      <div className="stripe-payment-status stripe-payment-success">
        <div className="stripe-payment-icon">&#10003;</div>
        <p>Payment confirmed!</p>
        <p className="stripe-payment-sub">Escrow is being funded on-chain...</p>
      </div>
    );
  }

  return (
    <div className="stripe-checkout-form">
      {/* Express Checkout (Apple Pay / Google Pay) */}
      <ExpressCheckoutElement
        onConfirm={handleExpressCheckout}
        options={{
          buttonType: { applePay: "buy", googlePay: "buy" },
          paymentMethods: { applePay: "always", googlePay: "always" },
        }}
      />

      <div className="stripe-divider">
        <span>or pay with card</span>
      </div>

      {/* Card payment fallback */}
      <PaymentElement
        options={{
          layout: "tabs",
        }}
      />

      <button
        className="stripe-pay-btn"
        onClick={confirmPayment}
        disabled={!stripe || paymentStatus === "processing"}
      >
        {paymentStatus === "processing"
          ? "Processing..."
          : `Pay $${amount.toFixed(2)}`}
      </button>
    </div>
  );
}

/* ── Main StripePayment wrapper ── */
export default function StripePayment({
  jobId,
  amount,
  agentAddress,
  boardJobId,
  onSuccess,
  onError,
}: StripePaymentProps) {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Stable ref for onError to avoid re-fetch loops when parent passes inline function
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    setLoading(true);
    setFetchError(null);

    fetch("/api/stripe/create-payment-intent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId, amount, agentAddress, boardJobId }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setClientSecret(data.clientSecret);
        setLoading(false);
      })
      .catch((err) => {
        setFetchError(err.message);
        setLoading(false);
        onErrorRef.current(`Failed to initialize payment: ${err.message}`);
      });
  }, [jobId, amount, agentAddress, boardJobId]);

  if (loading) {
    return (
      <div className="stripe-payment-container">
        <div className="stripe-payment-loading">
          <div className="stripe-spinner" />
          <p>Preparing payment...</p>
        </div>
      </div>
    );
  }

  if (fetchError || !clientSecret) {
    return (
      <div className="stripe-payment-container">
        <div className="stripe-payment-status stripe-payment-error">
          <p>Payment initialization failed</p>
          <p className="stripe-payment-sub">{fetchError}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="stripe-payment-container">
      <div className="stripe-payment-header">
        <h3>Fund Escrow</h3>
        <p className="stripe-payment-amount">${amount.toFixed(2)} USDC</p>
      </div>

      <Elements
        stripe={stripePromise}
        options={{
          clientSecret,
          appearance: {
            theme: "night",
            variables: {
              colorPrimary: "#6366f1",
              colorBackground: "#0f172a",
              colorText: "#f1f5f9",
              colorTextSecondary: "#94a3b8",
              colorDanger: "#ef4444",
              borderRadius: "8px",
              fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
            },
            rules: {
              ".Input": {
                backgroundColor: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              },
              ".Input:focus": {
                border: "1px solid #6366f1",
                boxShadow: "0 0 0 2px rgba(99, 102, 241, 0.25)",
              },
              ".Tab": {
                backgroundColor: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              },
              ".Tab--selected": {
                backgroundColor: "rgba(99, 102, 241, 0.15)",
                border: "1px solid #6366f1",
              },
            },
          },
        }}
      >
        <CheckoutForm
          amount={amount}
          onSuccess={onSuccess}
          onError={onError}
        />
      </Elements>
    </div>
  );
}
