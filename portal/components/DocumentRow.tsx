import { DocumentItem } from "@/lib/types";
import { FileText, Trash2, Clock, CheckCircle2 } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { useState } from "react";

interface DocumentRowProps {
  doc: DocumentItem;
  onDelete: (id: string) => Promise<void>;
}

export function DocumentRow({ doc, onDelete }: DocumentRowProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(doc.id);
    } finally {
      setIsDeleting(false);
      setShowConfirm(false);
    }
  };

  const filename = doc.metadata?.filename || doc.metadata?.file_name || doc.id;

  return (
    <div className="group flex items-center justify-between p-4 border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center border border-slate-700">
          <FileText className="w-5 h-5 text-slate-400" />
        </div>
        
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-medium text-slate-200">{filename}</h4>
            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] font-medium text-slate-400 border border-slate-700">
              {doc.metadata?.namespace || "global"}
            </span>
          </div>
          
          <div className="flex items-center gap-4 text-xs text-slate-500 mt-1.5">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              Indexed
            </span>
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {doc.metadata?.upload_time ? formatDate(new Date(doc.metadata.upload_time).getTime()) : "Unknown"}
            </span>
            <span>{doc.metadata?.total_chunks || 1} Chunks</span>
          </div>
        </div>
      </div>
      
      <div className="flex items-center gap-2">
        {showConfirm ? (
          <div className="flex items-center gap-2 bg-red-500/10 p-1.5 rounded-lg border border-red-500/20">
            <span className="text-xs font-medium text-red-400 px-2">Delete?</span>
            <button 
              onClick={handleDelete}
              disabled={isDeleting}
              className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
            >
              {isDeleting ? "..." : "Yes"}
            </button>
            <button 
              onClick={() => setShowConfirm(false)}
              disabled={isDeleting}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
            >
              No
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowConfirm(true)}
            className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
            title="Delete Document"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
