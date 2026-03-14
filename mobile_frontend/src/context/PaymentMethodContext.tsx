"use client";
import { createContext, useContext, useState, ReactNode } from "react";

type PaymentMethod = "stripe" | "usdc" | null;

interface PaymentMethodContextType {
  paymentMethod: PaymentMethod;
  setPaymentMethod: (method: PaymentMethod) => void;
}

const PaymentMethodContext = createContext<PaymentMethodContextType>({
  paymentMethod: null,
  setPaymentMethod: () => {},
});

export function PaymentMethodProvider({ children }: { children: ReactNode }) {
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>(null);
  return (
    <PaymentMethodContext.Provider value={{ paymentMethod, setPaymentMethod }}>
      {children}
    </PaymentMethodContext.Provider>
  );
}

export const usePaymentMethod = () => useContext(PaymentMethodContext);
export type { PaymentMethod };
