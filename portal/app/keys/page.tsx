"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { ApiKeyData } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { ApiKeyRow } from "@/components/ApiKeyRow";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Plus, KeyRound } from "lucide-react";

export default function KeysPage() {
  const { toast } = useToast();
  const [keys, setKeys] = useState<ApiKeyData[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Create Form State
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("client");
  const [newLimit, setNewLimit] = useState("100");
  const [newNamespace, setNewNamespace] = useState("global");
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.listApiKeys()
      .then((data) => {
        if (active) setKeys(data.keys);
      })
      .catch((error: unknown) => console.error(error))
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const fetchKeys = async () => {
    try {
      const data = await api.listApiKeys();
      setKeys(data.keys);
    } catch (err) {
      console.error(err);
      toast("Failed to load API keys", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName) return toast("Name is required", "error");
    
    setIsCreating(true);
    try {
      const result = await api.createApiKey({
        name: newName,
        role: newRole,
        rate_limit: parseInt(newLimit, 10),
        namespace: newNamespace,
      });
      
      setNewlyCreatedKey(result.key);
      toast("API Key created successfully", "success");
      setNewName("");
      fetchKeys(); // Refresh list
    } catch (err) {
      console.error(err);
      toast("Failed to create API key", "error");
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (keyPrefix: string) => {
    try {
      await api.revokeApiKey(keyPrefix);
      toast("API Key revoked", "success");
      fetchKeys(); // Refresh list
    } catch (err) {
      console.error(err);
      toast("Failed to revoke API key", "error");
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto w-full">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">API Keys</h1>
          <p className="text-slate-400">Manage access tokens for the SES Gateway.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Create Form */}
        <div className="lg:col-span-1">
          <div className="glass-panel rounded-xl p-6 sticky top-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center border border-blue-500/20">
                <Plus className="w-4 h-4 text-blue-400" />
              </div>
              <h2 className="text-lg font-semibold text-white">Create New Key</h2>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Key Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Production Web App"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus-ring placeholder-slate-600"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Role</label>
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus-ring"
                  >
                    <option value="client">Client</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Rate Limit</label>
                  <input
                    type="number"
                    value={newLimit}
                    onChange={(e) => setNewLimit(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus-ring"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Namespace</label>
                <input
                  type="text"
                  value={newNamespace}
                  onChange={(e) => setNewNamespace(e.target.value)}
                  placeholder="global"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus-ring placeholder-slate-600"
                />
              </div>

              <button
                type="submit"
                disabled={isCreating}
                className="w-full mt-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_15px_rgba(37,99,235,0.3)] text-sm font-medium transition-all disabled:opacity-50"
              >
                {isCreating ? "Creating..." : "Generate API Key"}
              </button>
            </form>
          </div>
        </div>

        {/* Key List */}
        <div className="lg:col-span-2">
          <div className="glass-panel rounded-xl overflow-hidden flex flex-col min-h-[400px]">
            <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center gap-3">
              <KeyRound className="w-4 h-4 text-slate-400" />
              <h3 className="font-medium text-slate-300">Active API Keys</h3>
            </div>
            
            <div className="flex-1 overflow-auto">
              {loading ? (
                <LoadingSpinner text="Loading keys..." />
              ) : keys.length === 0 ? (
                <div className="p-12 text-center text-slate-500">
                  No API keys found.
                </div>
              ) : (
                <div className="flex flex-col">
                  {keys.map((key) => (
                    <ApiKeyRow 
                      key={key.key} 
                      apiKey={key} 
                      onRevoke={handleRevoke}
                      fullKeyToCopy={
                        newlyCreatedKey && key.key.startsWith(newlyCreatedKey.slice(0, 15))
                          ? newlyCreatedKey
                          : undefined
                      }
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
