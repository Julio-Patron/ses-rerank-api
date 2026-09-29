import { AlertTriangle, RefreshCw, Settings } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

interface ConnectionErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ConnectionErrorState({ message, onRetry }: ConnectionErrorStateProps) {
  return (
    <EmptyState
      icon={AlertTriangle}
      title="Gateway unavailable"
      description={message}
      action={
        <div className="flex flex-wrap items-center justify-center gap-3">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          )}
          <a
            href="/settings"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700"
          >
            <Settings className="h-4 w-4" />
            Open Settings
          </a>
        </div>
      }
    />
  );
}
