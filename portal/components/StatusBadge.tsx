import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "healthy" | "degraded" | "down" | "connected" | "active" | "disabled" | "disconnected" | "unknown" | string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  
  let colorClass = "bg-slate-500/10 text-slate-400 border-slate-500/20";
  let dotClass = "bg-slate-400";

  if (["healthy", "connected", "active", "ok"].includes(normalized)) {
    colorClass = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    dotClass = "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]";
  } else if (["degraded", "warning"].includes(normalized)) {
    colorClass = "bg-amber-500/10 text-amber-400 border-amber-500/20";
    dotClass = "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]";
  } else if (["down", "disconnected", "error"].includes(normalized)) {
    colorClass = "bg-red-500/10 text-red-400 border-red-500/20";
    dotClass = "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.6)]";
  }

  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", colorClass)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", dotClass)} />
      {status.toUpperCase()}
    </span>
  );
}
