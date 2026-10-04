"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { claimCheckoutKey, storeCustomerKey } from "@/lib/billing";

function CheckoutSuccess() {
  const params = useSearchParams();
  const sessionId = params.get("session_id") ?? "";
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [message, setMessage] = useState(
    "Payment received. Credits are applied to the account that started checkout.",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onClaim() {
    if (!sessionId) {
      setError("Missing checkout session.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const claimed = await claimCheckoutKey(sessionId);
      if (!claimed) {
        setMessage("No new key was issued. Your existing key was topped up.");
        return;
      }
      storeCustomerKey(claimed);
      setApiKey(claimed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not claim the key");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold text-white">Payment received</h1>
      <p className="text-sm text-slate-300">{message}</p>
      <button
        type="button"
        onClick={onClaim}
        disabled={busy || !sessionId}
        className="w-fit rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
      >
        Reveal a new key if one was created
      </button>
      {apiKey && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
          Copy this key now. It will not be shown again: <span className="font-mono">{apiKey}</span>
        </p>
      )}
      {error && <p className="text-sm text-rose-300">{error}</p>}
      <a href="/billing" className="text-sm text-blue-300">Back to billing</a>
    </div>
  );
}

export default function BillingSuccessPage() {
  return (
    <Suspense fallback={<p className="px-6 py-16 text-sm text-slate-300">Loading checkout result…</p>}>
      <CheckoutSuccess />
    </Suspense>
  );
}
