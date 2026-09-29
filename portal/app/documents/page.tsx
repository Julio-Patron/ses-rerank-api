"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { DocumentItem } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { DocumentRow } from "@/components/DocumentRow";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { UploadCloud, FileText } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { ConnectionErrorState } from "@/components/ConnectionErrorState";
import { gatewayErrorMessage } from "@/lib/gateway-errors";

export default function DocumentsPage() {
  const { toast } = useToast();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    api.listDocuments(100)
      .then((data) => {
        if (active) setDocuments(data.documents || []);
      })
      .catch((error: unknown) => {
        console.error(error);
        if (active) {
          setDocuments([]);
          setLoadError(gatewayErrorMessage(error));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reloadKey]);

  const fetchDocuments = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.listDocuments(100);
      setDocuments(data.documents || []);
    } catch (err) {
      console.error(err);
      const message = gatewayErrorMessage(err);
      setDocuments([]);
      setLoadError(message);
      toast(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    try {
      await api.ingestFile(file);
      toast(`Successfully uploaded ${file.name}`, "success");
      fetchDocuments();
    } catch (err) {
      console.error(err);
      toast(`${file.name}: ${gatewayErrorMessage(err)}`, "error");
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    if (fileInputRef.current) fileInputRef.current.value = ""; // reset
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteDocument(id);
      toast("Document deleted", "success");
      await fetchDocuments();
    } catch (err) {
      console.error(err);
      toast(gatewayErrorMessage(err), "error");
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">Knowledge Base</h1>
        <p className="text-slate-400">Manage your indexed documents and files.</p>
      </div>

      <div 
        className={`mb-8 rounded-2xl border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center p-12 relative overflow-hidden ${
          isDragging 
            ? "border-blue-500 bg-blue-500/10 scale-[1.02] shadow-[0_0_30px_rgba(59,130,246,0.2)]" 
            : "border-slate-700 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-900/50"
        }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
        onDrop={handleDrop}
      >
        {isUploading ? (
          <LoadingSpinner text="Uploading and indexing document..." />
        ) : (
          <>
            <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors ${isDragging ? "bg-blue-500/20" : "bg-slate-800"}`}>
              <UploadCloud className={`w-8 h-8 ${isDragging ? "text-blue-400" : "text-slate-400"}`} />
            </div>
            <h3 className="text-lg font-medium text-white mb-2">Drop a PDF, TXT, or DOCX here</h3>
            <p className="text-slate-400 text-sm mb-6 text-center max-w-sm">
              The file will be automatically parsed, chunked, and embedded into the vector store.
            </p>
            <button 
              onClick={() => fileInputRef.current?.click()}
              className="px-6 py-2.5 rounded-full bg-slate-800 hover:bg-slate-700 text-white font-medium border border-slate-700 transition-colors shadow-sm"
            >
              Browse Files
            </button>
            <input 
              type="file" 
              ref={fileInputRef} 
              className="hidden" 
              accept=".pdf,.txt,.docx,.md"
              onChange={handleFileSelect}
            />
          </>
        )}
      </div>

      <div className="glass-panel rounded-xl overflow-hidden flex flex-col min-h-[400px]">
        <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center gap-3">
          <FileText className="w-4 h-4 text-slate-400" />
          <h3 className="font-medium text-slate-300">
            Indexed Documents ({loading ? "…" : loadError ? "Unavailable" : documents.length})
          </h3>
        </div>
        
        <div className="flex-1 overflow-auto">
          {loading ? (
            <LoadingSpinner text="Loading documents..." />
          ) : loadError ? (
            <ConnectionErrorState
              message={loadError}
              onRetry={() => {
                setLoading(true);
                setLoadError(null);
                setReloadKey((value) => value + 1);
              }}
            />
          ) : documents.length === 0 ? (
            <EmptyState 
              icon={FileText}
              title="No documents yet"
              description="Upload your first document above to start building your knowledge base."
            />
          ) : (
            <div className="flex flex-col">
              {documents.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} onDelete={handleDelete} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
