"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";
import { CheckCircle, XCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error";

interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  toast: (message: string, type: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = (message: string, type: ToastType) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "flex items-center gap-3 rounded-lg p-4 text-white shadow-lg backdrop-blur-md transition-all",
              t.type === "success"
                ? "bg-emerald-500/80 border border-emerald-400/50"
                : "bg-red-500/80 border border-red-400/50"
            )}
          >
            {t.type === "success" ? (
              <CheckCircle className="h-5 w-5 text-emerald-100" />
            ) : (
              <XCircle className="h-5 w-5 text-red-100" />
            )}
            <p className="text-sm font-medium">{t.message}</p>
            <button
              onClick={() => setToasts((prev) => prev.filter((to) => to.id !== t.id))}
              className="ml-2 text-white/70 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
};
