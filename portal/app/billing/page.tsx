"use client";

import { FormEvent, useState } from "react";
import {
  fetchUsage,
  loadCustomerKey,
  signup,
  startCheckout,
  storeCustomerKey,
  type CreditPack,
  type UsageSnapshot,
} from "@/lib/billing";

export default function BillingPage() {
  const [email, setEmail] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [issuedKey, setIssuedKey] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSignup(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await signup(email.trim());
      storeCustomerKey(created.api_key);
      setIssuedKey(created.api_key);
      setApiKey(created.api_key);
      setUsage(await fetchUsage(created.api_key));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  async function onLoadUsage(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const key = apiKey.trim() || loadCustomerKey();
      storeCustomerKey(key);
      setUsage(await fetchUsage(key));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load balance");
    } finally {
      setBusy(false);
    }
  }

  async function onBuy(pack: CreditPack) {
    setBusy(true);
    setError(null);
    try {
      const key = apiKey.trim() || loadCustomerKey();
      if (!key) throw new Error("Create or paste an API key before buying credits.");
      const url = await startCheckout(key, pack);
      window.location.assign(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="text-sm font-medium text-blue-300">Customer billing</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">Buy credits</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          Create a key, check the balance, and buy a credit pack. This page is separate from the operator console.
        </p>
      </header>

      <section className="rounded-2xl border border-white/10 bg-slate-950/60 p-6">
        <h2 className="text-lg font-medium text-white">Create an account</h2>
        <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={onSignup}>
          <label className="sr-only" htmlFor="billing-email">Email</label>
          <input
            id="billing-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            className="flex-1 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            Get a free key
          </button>
        </form>
        {issuedKey && (
          <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
            Copy this key now. It will not be shown again: <span className="font-mono">{issuedKey}</span>
          </p>
        )}
      </section>

      <section className="rounded-2xl border border-white/10 bg-slate-950/60 p-6">
        <h2 className="text-lg font-medium text-white">Balance</h2>
        <form className="mt-4 flex flex-col gap-3" onSubmit={onLoadUsage}>
          <label className="text-sm text-slate-300" htmlFor="billing-key">API key</label>
          <input
            id="billing-key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            autoComplete="off"
            className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"
          />
          <button
            type="submit"
            disabled={busy}
            className="w-fit rounded-lg border border-white/10 px-4 py-2 text-sm text-white disabled:opacity-60"
          >
            Check balance
          </button>
        </form>
        {usage && (
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-slate-400">Account</dt>
              <dd className="text-white">{usage.account_name}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Plan</dt>
              <dd className="text-white">{usage.plan_tier}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Credits</dt>
              <dd className="text-white">{usage.credits_remaining}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Tokens saved</dt>
              <dd className="text-white">{usage.tokens_saved_total}</dd>
            </div>
          </dl>
        )}
      </section>

      <section className="rounded-2xl border border-white/10 bg-slate-950/60 p-6">
        <h2 className="text-lg font-medium text-white">Credit packs</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onBuy("developer")}
            className="rounded-xl border border-white/10 p-4 text-left hover:border-blue-500/40 disabled:opacity-60"
          >
            <span className="block text-white">Developer</span>
            <span className="mt-1 block text-sm text-slate-400">10,000 credits</span>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onBuy("growth")}
            className="rounded-xl border border-white/10 p-4 text-left hover:border-blue-500/40 disabled:opacity-60"
          >
            <span className="block text-white">Growth</span>
            <span className="mt-1 block text-sm text-slate-400">100,000 credits</span>
          </button>
        </div>
      </section>

      {error && <p className="text-sm text-rose-300">{error}</p>}
    </div>
  );
}
