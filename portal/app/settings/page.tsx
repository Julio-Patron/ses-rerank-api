"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Save, Server, KeyRound, CheckCircle2 } from "lucide-react";
import { gatewayErrorMessage } from "@/lib/gateway-errors";

export default function SettingsPage() {
  const { toast } = useToast();
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [apiKey, setApiKey] = useState("");
  const [isTesting, setIsTesting] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "success" | "degraded" | "error">("idle");
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setApiUrl(localStorage.getItem("ses_api_url") || "http://localhost:8000");
      setApiKey(localStorage.getItem("ses_api_key") || "");
    }, 0);
    return () => window.clearTimeout(timeout);
  }, []);

  const handleSave = () => {
    localStorage.setItem("ses_api_url", apiUrl);
    localStorage.setItem("ses_api_key", apiKey);
    toast("Settings saved successfully", "success");
    setTestStatus("idle");
  };

  const handleTestConnection = async () => {
    // Save first so the api client uses the new values
    localStorage.setItem("ses_api_url", apiUrl);
    localStorage.setItem("ses_api_key", apiKey);
    
    setIsTesting(true);
    setTestStatus("idle");
    setTestError(null);
    
    try {
      const [health] = await Promise.all([api.getHealth(), api.getAnalytics()]);
      if (health.status === "healthy") {
        setTestStatus("success");
        toast("Connection successful!", "success");
      } else {
        const message = "Gateway connected, but one or more required services are degraded.";
        setTestStatus("degraded");
        setTestError(message);
        toast(message, "error");
      }
    } catch (err) {
      console.error(err);
      const message = gatewayErrorMessage(err);
      setTestStatus("error");
      setTestError(message);
      toast(message, "error");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">Settings</h1>
        <p className="text-slate-400">Configure your connection to the SES Enterprise Gateway.</p>
      </div>

      <div className="glass-panel rounded-xl p-8 max-w-2xl">
        <div className="space-y-6">
          
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-2">
              <Server className="w-4 h-4 text-blue-400" />
              API Endpoint URL
            </label>
            <input
              type="text"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-slate-200 focus-ring placeholder-slate-600 transition-all"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-2">
              <KeyRound className="w-4 h-4 text-purple-400" />
              Admin API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="ses_..."
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-slate-200 focus-ring placeholder-slate-600 transition-all font-mono"
            />
            <p className="text-xs text-slate-500 mt-2">
              Requires an API key with the &apos;admin&apos; role to access all portal features.
            </p>
          </div>

        </div>

        <div className="mt-10 pt-6 border-t border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={handleTestConnection}
              disabled={isTesting}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isTesting ? "Testing..." : "Test Connection"}
            </button>
            
            {testStatus === "success" && (
              <span className="flex items-center gap-1.5 text-sm text-emerald-400">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            )}
            {testStatus === "degraded" && (
              <span className="text-sm font-medium text-amber-400">Connected · Degraded</span>
            )}
          </div>
          
          <button
            onClick={handleSave}
            className="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.4)] text-sm font-medium transition-all flex items-center gap-2"
          >
            <Save className="w-4 h-4" />
            Save Settings
          </button>
        </div>
        {testError && (
          <p role="alert" className="mt-4 text-sm text-amber-300">
            {testError}
          </p>
        )}
      </div>
    </div>
  );
}
