"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { 
  LayoutDashboard, 
  Search, 
  FileText, 
  BarChart3, 
  KeyRound, 
  FileBox, 
  Settings 
} from "lucide-react";

const navItems = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/search", icon: Search, label: "RAG Search" },
  { href: "/documents", icon: FileText, label: "Documents" },
  { href: "/analytics", icon: BarChart3, label: "Analytics" },
  { href: "/keys", icon: KeyRound, label: "API Keys" },
  { href: "/reports", icon: FileBox, label: "Reports" },
  { href: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-white/10 bg-slate-950/50 backdrop-blur-xl h-screen sticky top-0 flex flex-col hidden md:flex">
      <div className="p-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <div className="w-4 h-4 bg-white rounded-sm" />
          </div>
          <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
            SES Gateway
          </h1>
        </div>
      </div>

      <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group relative overflow-hidden",
                isActive
                  ? "text-white bg-blue-600/10 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              )}
            >
              {isActive && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 rounded-r-full" />
              )}
              <item.icon
                className={cn(
                  "w-5 h-5 transition-colors",
                  isActive ? "text-blue-400" : "text-slate-500 group-hover:text-slate-300"
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 mt-auto">
        <div className="p-4 rounded-xl bg-gradient-to-br from-blue-900/40 to-slate-900 border border-blue-800/30">
          <p className="text-xs font-medium text-blue-200 mb-1">Enterprise Edition</p>
          <p className="text-[10px] text-slate-400">Version 2.0.0</p>
        </div>
      </div>
    </aside>
  );
}
