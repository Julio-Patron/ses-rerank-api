import { ApiKeyData } from "@/lib/types";
import { KeyRound, Trash2, Copy, ShieldAlert } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { useState } from "react";
import { useToast } from "./Toast";

interface ApiKeyRowProps {
  apiKey: ApiKeyData;
  onRevoke: (key: string) => Promise<void>;
  fullKeyToCopy?: string | null;
}

export function ApiKeyRow({ apiKey, onRevoke, fullKeyToCopy }: ApiKeyRowProps) {
  const { toast } = useToast();
  const [isRevoking, setIsRevoking] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleRevoke = async () => {
    setIsRevoking(true);
    try {
      await onRevoke(apiKey.key);
    } finally {
      setIsRevoking(false);
      setShowConfirm(false);
    }
  };

  const handleCopy = () => {
    if (fullKeyToCopy) {
      navigator.clipboard.writeText(fullKeyToCopy);
      toast("API key copied to clipboard", "success");
    }
  };

  const isAdmin = apiKey.role === "admin";

  return (
    <div className="group flex flex-col p-4 border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
            isAdmin ? "bg-purple-500/10 border-purple-500/20" : "bg-blue-500/10 border-blue-500/20"
          }`}>
            {isAdmin ? <ShieldAlert className="w-5 h-5 text-purple-400" /> : <KeyRound className="w-5 h-5 text-blue-400" />}
          </div>
          
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-medium text-slate-200">{apiKey.name}</h4>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                isAdmin ? "bg-purple-500/10 text-purple-400 border-purple-500/20" : "bg-blue-500/10 text-blue-400 border-blue-500/20"
              }`}>
                {apiKey.role.toUpperCase()}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] font-medium text-slate-400 border border-slate-700">
                {apiKey.namespace}
              </span>
            </div>
            
            <div className="flex items-center gap-4 text-xs text-slate-500 mt-1.5">
              <code className="px-1.5 py-0.5 rounded bg-slate-900 font-mono text-[11px] text-slate-400 border border-slate-800">
                {apiKey.key}
              </code>
              <span>Limit: {apiKey.rate_limit}/min</span>
              <span>Created {formatDate(apiKey.created_at)}</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {showConfirm ? (
            <div className="flex items-center gap-2 bg-red-500/10 p-1.5 rounded-lg border border-red-500/20">
              <span className="text-xs font-medium text-red-400 px-2">Revoke?</span>
              <button 
                onClick={handleRevoke}
                disabled={isRevoking}
                className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
              >
                {isRevoking ? "..." : "Yes"}
              </button>
              <button 
                onClick={() => setShowConfirm(false)}
                disabled={isRevoking}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConfirm(true)}
              className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
              title="Revoke Key"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {fullKeyToCopy && (
        <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-amber-400 mb-1">Copy this key now. You won&apos;t be able to see it again.</p>
            <code className="text-sm font-mono text-white break-all">{fullKeyToCopy}</code>
          </div>
          <button 
            onClick={handleCopy}
            className="ml-4 p-2 bg-slate-800 hover:bg-slate-700 rounded-md text-white transition-colors flex-shrink-0"
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
