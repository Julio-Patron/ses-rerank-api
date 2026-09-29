"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AnalyticsData, HealthResponse } from "@/lib/types";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ConnectionErrorState } from "@/components/ConnectionErrorState";
import { gatewayErrorMessage } from "@/lib/gateway-errors";
import { Search, Database, Zap, KeyRound, Activity } from "lucide-react";

export default function DashboardPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError(null);
      try {
        const [analyticsData, healthData] = await Promise.all([
          api.getAnalytics(),
          api.getHealth()
        ]);
        setAnalytics(analyticsData);
        setHealth(healthData);
      } catch (err) {
        console.error(err);
        setAnalytics(null);
        setHealth(null);
        setError(gatewayErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [reloadKey]);

  if (loading) return <LoadingSpinner text="Loading dashboard metrics..." />;

  return (
    <div className="p-8 max-w-7xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
        <p className="text-slate-400">Overview of your SES Enterprise Gateway.</p>
      </div>

      {error ? (
        <ConnectionErrorState
          message={error}
          onRetry={() => setReloadKey((value) => value + 1)}
        />
      ) : (
        <>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Total Searches"
          value={analytics?.total_searches || 0}
          icon={Search}
        />
        <MetricCard
          title="Total Ingestions"
          value={analytics?.total_ingestions || 0}
          icon={Database}
        />
        <MetricCard
          title="Avg Latency"
          value={`${analytics?.average_latency_ms?.toFixed(1) || 0} ms`}
          icon={Zap}
        />
        <MetricCard
          title="Active Keys"
          value={analytics?.keys_performance?.length || 0}
          icon={KeyRound}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 glass-panel rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Activity className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-white">System Health</h2>
          </div>
          
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-800">
              <span className="font-medium text-slate-300">Overall Status</span>
              <StatusBadge status={health?.status || "unknown"} />
            </div>
            
            {health?.services && Object.entries(health.services).map(([key, status]) => (
              <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-800">
                <span className="text-sm text-slate-400 capitalize">{key.replace("_", " ")}</span>
                <StatusBadge status={status} />
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-2 glass-panel rounded-xl p-6 flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-white">Recent Activity Logs</h2>
          </div>
          
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-400 uppercase bg-slate-900/50 border-y border-slate-800">
                <tr>
                  <th className="px-4 py-3 font-medium">Timestamp</th>
                  <th className="px-4 py-3 font-medium">Endpoint</th>
                  <th className="px-4 py-3 font-medium">Key</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-right">Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {analytics?.recent_logs?.slice(0, 8).map((log, i) => (
                  <tr key={i} className="hover:bg-slate-800/20 transition-colors">
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-300">
                      {log.endpoint}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {log.key_name}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                        log.status_code < 400 ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                      }`}>
                        {log.status_code}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-slate-400">
                      {log.latency_ms.toFixed(0)} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {(!analytics?.recent_logs || analytics.recent_logs.length === 0) && (
              <div className="text-center p-8 text-slate-500 text-sm">
                No recent activity logged.
              </div>
            )}
          </div>
        </div>
      </div>
        </>
      )}
    </div>
  );
}
