"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useAuth } from "@/src/context/AuthContext";

export default function AuthScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "register") {
        await register(email, password, name);
      } else {
        await login(email, password);
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-6">
      <motion.div
        className="w-full max-w-sm"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <h1
            className="text-2xl font-bold mb-1"
            style={{
              background: "linear-gradient(135deg, #6366f1, #a78bfa)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            SOTA Butler
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {mode === "login" ? "Sign in to continue" : "Create your account"}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <AnimatePresence mode="wait">
            {mode === "register" && (
              <motion.input
                key="name"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                type="text"
                placeholder="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="auth-input"
              />
            )}
          </AnimatePresence>

          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="auth-input"
          />

          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="auth-input"
          />

          {/* Error message */}
          <AnimatePresence>
            {error && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="text-sm text-center"
                style={{ color: "var(--red)" }}
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <button
            type="submit"
            disabled={loading}
            className="auth-submit mt-2"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <span
                  className="inline-block w-4 h-4 border-2 rounded-full animate-spin"
                  style={{
                    borderColor: "rgba(255,255,255,0.3)",
                    borderTopColor: "#fff",
                  }}
                />
                {mode === "login" ? "Signing in..." : "Creating account..."}
              </span>
            ) : mode === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        {/* Toggle mode */}
        <p
          className="text-center text-sm mt-5"
          style={{ color: "var(--text-muted)" }}
        >
          {mode === "login" ? "Don't have an account?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
              setEmail("");
              setPassword("");
              setName("");
            }}
            className="font-medium hover:underline"
            style={{ color: "var(--accent)", background: "none", border: "none", cursor: "pointer" }}
          >
            {mode === "login" ? "Sign Up" : "Sign In"}
          </button>
        </p>
      </motion.div>
    </div>
  );
}
