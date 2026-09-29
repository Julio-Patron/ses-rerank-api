"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { FileBox, Download, Activity, FileText } from "lucide-react";

export default function ReportsPage() {
  const { toast } = useToast();
  const [isGeneratingUsage, setIsGeneratingUsage] = useState(false);
  const [isGeneratingHealth, setIsGeneratingHealth] = useState(false);

  const handleGenerateUsage = async () => {
    setIsGeneratingUsage(true);
    try {
      await api.downloadReport("/api/v1/admin/reports/usage");
      toast("Usage report generated successfully", "success");
    } catch (err) {
      console.error(err);
      toast("Failed to generate usage report", "error");
    } finally {
      setIsGeneratingUsage(false);
    }
  };

  const handleGenerateHealth = async () => {
    setIsGeneratingHealth(true);
    try {
      await api.downloadReport("/api/v1/admin/reports/health");
      toast("Health report generated successfully", "success");
    } catch (err) {
      console.error(err);
      toast("Failed to generate health report", "error");
    } finally {
      setIsGeneratingHealth(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto w-full">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Corporate Reports</h1>
          <p className="text-slate-400">Generate and download audit, compliance, and system reports in PDF format.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Usage Analytics Report */}
        <div className="glass-panel rounded-xl p-8 flex flex-col items-center text-center relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl -mr-16 -mt-16 transition-all group-hover:bg-blue-500/10"></div>
          
          <div className="w-16 h-16 rounded-2xl bg-blue-500/10 flex items-center justify-center border border-blue-500/20 mb-6 shadow-inner relative z-10">
            <FileBox className="w-8 h-8 text-blue-400" />
          </div>
          
          <h2 className="text-xl font-bold text-white mb-3 relative z-10">Usage & Billing Analytics</h2>
          <p className="text-slate-400 text-sm mb-8 max-w-sm relative z-10 leading-relaxed">
            Generates a comprehensive PDF detailing API usage, token consumption, and latency metrics across all keys for the current billing period.
          </p>
          
          <button
            onClick={handleGenerateUsage}
            disabled={isGeneratingUsage}
            className="mt-auto flex items-center gap-2 px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium shadow-[0_0_20px_rgba(37,99,235,0.3)] transition-all disabled:opacity-50 relative z-10"
          >
            {isGeneratingUsage ? (
              "Generating PDF..."
            ) : (
              <>
                <Download className="w-5 h-5" />
                Generate Usage Report
              </>
            )}
          </button>
        </div>

        {/* System Health Report */}
        <div className="glass-panel rounded-xl p-8 flex flex-col items-center text-center relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full blur-3xl -mr-16 -mt-16 transition-all group-hover:bg-emerald-500/10"></div>
          
          <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 mb-6 shadow-inner relative z-10">
            <Activity className="w-8 h-8 text-emerald-400" />
          </div>
          
          <h2 className="text-xl font-bold text-white mb-3 relative z-10">System Health Snapshot</h2>
          <p className="text-slate-400 text-sm mb-8 max-w-sm relative z-10 leading-relaxed">
            Generates an IT operations PDF showing current service status (Qdrant, Redis, Rust Acceleration) along with recent error traces and uptime metrics.
          </p>
          
          <button
            onClick={handleGenerateHealth}
            disabled={isGeneratingHealth}
            className="mt-auto flex items-center gap-2 px-6 py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all disabled:opacity-50 relative z-10"
          >
            {isGeneratingHealth ? (
              "Generating PDF..."
            ) : (
              <>
                <Download className="w-5 h-5" />
                Generate Health Report
              </>
            )}
          </button>
        </div>

        {/* Evidence Audit Note */}
        <div className="md:col-span-2 glass-panel rounded-xl p-6 flex items-start gap-4 border-l-4 border-l-purple-500">
          <FileText className="w-6 h-6 text-purple-400 shrink-0 mt-1" />
          <div>
            <h3 className="font-semibold text-white mb-1">Looking for Evidence Audit Reports?</h3>
            <p className="text-slate-400 text-sm">
              Semantic Evidence Audit Reports are generated on a per-query basis. To generate one, go to the <a href="/search" className="text-purple-400 hover:underline">RAG Search</a> page, execute a query, and click &quot;Export Audit PDF&quot; on the results panel.
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
