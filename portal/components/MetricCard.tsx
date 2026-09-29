import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}

export function MetricCard({ title, value, icon: Icon, trend, className }: MetricCardProps) {
  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-slate-900/50 backdrop-blur-sm border border-slate-800 p-6 shadow-sm", className)}>
      <div className="absolute top-0 right-0 p-4 opacity-10">
        <Icon className="w-16 h-16" />
      </div>
      
      <div className="relative z-10 flex flex-col gap-4">
        <div className="flex items-center gap-2 text-slate-400">
          <Icon className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-medium">{title}</h3>
        </div>
        
        <div className="flex items-end justify-between">
          <div className="text-3xl font-bold text-white">{value}</div>
          
          {trend && (
            <div className={cn(
              "text-xs font-medium px-2 py-1 rounded-full",
              trend.isPositive ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
            )}>
              {trend.isPositive ? "+" : "-"}{Math.abs(trend.value)}%
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
