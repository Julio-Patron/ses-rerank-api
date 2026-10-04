const CUSTOMER_KEY_STORAGE = "ses_customer_api_key";
const DEFAULT_API_URL = process.env.NEXT_PUBLIC_SES_API_URL ?? "http://127.0.0.1:8000";

export type CreditPack = "developer" | "growth";

export type UsageSnapshot = {
  account_name: string;
  plan_tier: string;
  credits_remaining: number;
  tokens_saved_total: number;
  rate_limit: number;
};

function gatewayUrl(): string {
  return DEFAULT_API_URL.replace(/\/+$/, "");
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (typeof body.message === "string") return body.message;
  } catch {
    return "Request failed";
  }
  return "Request failed";
}

export function loadCustomerKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(CUSTOMER_KEY_STORAGE) ?? "";
}

export function storeCustomerKey(apiKey: string): void {
  window.localStorage.setItem(CUSTOMER_KEY_STORAGE, apiKey);
}

export async function signup(email: string): Promise<{ api_key: string; credits: number; plan_tier: string }> {
  const response = await fetch(`${gatewayUrl()}/v1/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchUsage(apiKey: string): Promise<UsageSnapshot> {
  const response = await fetch(`${gatewayUrl()}/v1/usage`, {
    headers: { Accept: "application/json", Authorization: `Bearer ${apiKey}` },
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function startCheckout(apiKey: string, pack: CreditPack): Promise<string> {
  const response = await fetch(`${gatewayUrl()}/v1/billing/checkout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ pack }),
  });
  if (!response.ok) throw new Error(await readError(response));
  const body = await response.json();
  if (typeof body.url !== "string" || !body.url) throw new Error("Checkout did not return a URL");
  return body.url;
}

export async function claimCheckoutKey(sessionId: string): Promise<string | null> {
  const response = await fetch(`${gatewayUrl()}/v1/billing/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await readError(response));
  const body = await response.json();
  return typeof body.api_key === "string" ? body.api_key : null;
}
