"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { AnalyticsData } from "@/lib/types";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from "recharts";
import { Download } from "lucide-react";

const COLORS = ['#3b82f6', '#06b6d4', '#8b5cf6', '#10b981'];

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.getAnalytics()
      .then((data) => {
        if (active) setAnalytics(data);
      })
      .catch((error: unknown) => console.error(error))
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) return <LoadingSpinner text="Loading analytics data..." />;
  if (!analytics) return <div className="p-8 text-slate-500">Failed to load analytics data.</div>;

  // Process data for charts
  const requestDistribution = [
    { name: 'Searches', value: analytics.total_searches },
    { name: 'Ingestions', value: analytics.total_ingestions },
  ].filter(d => d.value > 0);

  const timelineData = Array.from(
    analytics.recent_logs.reduce((buckets, log) => {
      const date = new Date(log.timestamp);
      if (Number.isNaN(date.getTime())) return buckets;

      const key = date.toISOString().slice(0, 10);
      const current = buckets.get(key) || {
        key,
        name: date.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        requests: 0,
        errors: 0,
      };
      current.requests += 1;
      if (log.status_code >= 400) current.errors += 1;
      buckets.set(key, current);
      return buckets;
    }, new Map<string, { key: string; name: string; requests: number; errors: number }>()).values(),
  )
    .sort((a, b) => a.key.localeCompare(b.key))
    .slice(-7);

  return (
    <div className="p-8 max-w-7xl mx-auto w-full">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Analytics</h1>
          <p className="text-slate-400">Deep dive into usage metrics and performance.</p>
        </div>
        <button 
          onClick={() => {
             const csv = [
               ["Metric", "Value"],
               ["Total Requests", analytics.total_requests],
               ["Total Errors", analytics.total_errors],
               ["Total Searches", analytics.total_searches],
               ["Total Ingestions", analytics.total_ingestions],
               ["Average Latency (ms)", analytics.average_latency_ms]
             ].map(e => e.join(",")).join("\n");
             
             const blob = new Blob([csv], { type: 'text/csv' });
             const url = window.URL.createObjectURL(blob);
             const a = document.createElement("a");
             a.href = url;
             a.download = "ses_analytics.csv";
             a.click();
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors border border-slate-700"
        >
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Timeline Chart */}
        <div className="lg:col-span-2 glass-panel rounded-xl p-6 min-h-[350px] flex flex-col">
          <h3 className="text-lg font-medium text-white mb-6">Observed Request Volume</h3>
          <div className="flex-1 w-full min-h-[250px]">
            {timelineData.length > 0 ? <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timelineData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "0.5rem" }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
                <Line type="monotone" dataKey="requests" name="Total Requests" stroke="#3b82f6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                <Line type="monotone" dataKey="errors" name="Errors" stroke="#ef4444" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer> : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                No persisted request history is available yet.
              </div>
            )}
          </div>
        </div>

        {/* Distribution Chart */}
        <div className="lg:col-span-1 glass-panel rounded-xl p-6 flex flex-col">
          <h3 className="text-lg font-medium text-white mb-6">Request Distribution</h3>
          <div className="flex-1 w-full min-h-[250px] flex items-center justify-center">
            {requestDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={requestDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {requestDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "0.5rem" }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-slate-500 text-sm">No distribution data available</div>
            )}
          </div>
        </div>
      </div>

      {/* Key Performance Table */}
      <div className="glass-panel rounded-xl p-6">
        <h3 className="text-lg font-medium text-white mb-6">API Key Performance</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-400 uppercase bg-slate-900/50 border-y border-slate-800">
              <tr>
                <th className="px-4 py-3 font-medium">Key Name</th>
                <th className="px-4 py-3 font-medium">Namespace</th>
                <th className="px-4 py-3 font-medium text-center">Role</th>
                <th className="px-4 py-3 font-medium text-right">Total Calls</th>
                <th className="px-4 py-3 font-medium text-right">Avg Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {analytics.keys_performance.map((kp, i) => (
                <tr key={i} className="hover:bg-slate-800/20 transition-colors">
                  <td className="px-4 py-4 font-medium text-slate-300">
                    {kp.name}
                  </td>
                  <td className="px-4 py-4 text-slate-400">
                    <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] border border-slate-700">
                      {kp.namespace}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                      kp.role === 'admin' ? "bg-purple-500/10 text-purple-400 border-purple-500/20" : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                    }`}>
                      {kp.role.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-right font-medium text-slate-300">
                    {kp.total_calls.toLocaleString()}
                  </td>
                  <td className="px-4 py-4 text-right text-slate-400">
                    {kp.avg_latency_ms.toFixed(1)} ms
                  </td>
                </tr>
              ))}
              {analytics.keys_performance.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                    No API keys have recorded usage yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
