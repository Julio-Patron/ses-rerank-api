import { SearchResultItem } from "@/lib/types";
import { FileText, Hash, Clock } from "lucide-react";
import { formatDate } from "@/lib/utils";

export function SearchResult({ result }: { result: SearchResultItem }) {
  const scorePct = Math.round(result.score * 100);
  
  let scoreColor = "bg-emerald-500";
  if (result.score < 0.5) scoreColor = "bg-red-500";
  else if (result.score < 0.8) scoreColor = "bg-amber-500";

  const filename = result.metadata?.filename || result.metadata?.file_name || "Unknown file";

  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-5 hover:border-slate-700 transition-colors">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center border border-blue-500/20">
            <FileText className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h4 className="font-medium text-slate-200">{filename}</h4>
            <div className="flex items-center gap-4 text-xs text-slate-500 mt-1">
              {result.metadata?.chunk_index !== undefined && (
                <span className="flex items-center gap-1">
                  <Hash className="w-3 h-3" /> Chunk {result.metadata.chunk_index}
                </span>
              )}
              {result.indexed_at && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {formatDate(result.indexed_at)}
                </span>
              )}
            </div>
          </div>
        </div>
        
        <div className="flex flex-col items-end gap-1">
          <span className="text-sm font-bold text-slate-300">{scorePct}% Match</span>
          <div className="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div 
              className={`h-full ${scoreColor} shadow-[0_0_8px_rgba(255,255,255,0.2)]`} 
              style={{ width: `${scorePct}%` }} 
            />
          </div>
        </div>
      </div>
      
      <div className="bg-slate-950 rounded-lg p-4 text-sm text-slate-300 leading-relaxed border border-slate-800/50">
        <span className="italic">&ldquo;</span>
        {result.text_snippet || result.text}
        <span className="italic">&rdquo;</span>
      </div>
    </div>
  );
}
