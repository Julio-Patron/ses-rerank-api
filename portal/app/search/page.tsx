"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { SearchResultItem } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { SearchResult } from "@/components/SearchResult";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { ConnectionErrorState } from "@/components/ConnectionErrorState";
import { gatewayErrorMessage } from "@/lib/gateway-errors";
import { Search as SearchIcon, FileBox, Zap, BrainCircuit } from "lucide-react";

export default function SearchPage() {
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [answer, setAnswer] = useState<string | null>(null);
  const [searchStats, setSearchStats] = useState<{ searchTime: number, totalTime: number, rustUsed: boolean } | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  
  // Options
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.5);
  const [generateAnswer, setGenerateAnswer] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setAnswer(null);
    setSearchStats(null);
    setResults([]);
    setSearchError(null);

    try {
      const data = await api.search({
        query,
        top_k: topK,
        threshold,
        generate_answer: generateAnswer
      });

      setResults(data.results || []);
      setAnswer(data.answer || null);
      setSearchStats({
        searchTime: data.search_time_ms,
        totalTime: data.total_time_ms,
        rustUsed: data.rust_accelerated
      });
      
    } catch (err) {
      console.error(err);
      const message = gatewayErrorMessage(err);
      setSearchError(message);
      toast(message, "error");
    } finally {
      setIsSearching(false);
    }
  };

  const handleGenerateReport = async () => {
    if (!query.trim() || results.length === 0) return;
    
    setIsDownloading(true);
    try {
      await api.downloadReport("/api/v1/reports/evidence", {
        query,
        top_k: topK,
        threshold,
        generate_answer: generateAnswer
      });
      toast("Report generated and downloaded successfully", "success");
    } catch (err) {
      console.error(err);
      toast(gatewayErrorMessage(err), "error");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto w-full h-full flex flex-col">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">RAG Search</h1>
        <p className="text-slate-400">Query your knowledge base with semantic search and LLM synthesis.</p>
      </div>

      <div className="glass-panel rounded-xl p-6 mb-6">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <SearchIcon className="h-5 w-5 text-slate-500" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question about your documents..."
              className="w-full bg-slate-900 border border-slate-700 rounded-xl pl-11 pr-4 py-4 text-slate-200 focus-ring placeholder-slate-500 text-lg transition-all shadow-inner"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="px-8 py-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium shadow-[0_0_20px_rgba(37,99,235,0.3)] transition-all disabled:opacity-50 disabled:shadow-none"
          >
            {isSearching ? "Searching..." : "Search"}
          </button>
        </form>

        <div className="mt-6 pt-6 border-t border-slate-800 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="flex items-center justify-between text-sm font-medium text-slate-300 mb-2">
              <span>Top K Results: <span className="text-blue-400">{topK}</span></span>
            </label>
            <input 
              type="range" 
              min="1" max="20" 
              value={topK} 
              onChange={(e) => setTopK(parseInt(e.target.value))}
              className="w-full accent-blue-500"
            />
          </div>
          
          <div>
            <label className="flex items-center justify-between text-sm font-medium text-slate-300 mb-2">
              <span>Similarity Threshold: <span className="text-blue-400">{threshold}</span></span>
            </label>
            <input 
              type="range" 
              min="0" max="1" step="0.05"
              value={threshold} 
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full accent-blue-500"
            />
          </div>

          <div className="flex items-center justify-end md:mt-6">
            <label className="flex items-center gap-3 cursor-pointer">
              <div className="relative">
                <input 
                  type="checkbox" 
                  className="sr-only" 
                  checked={generateAnswer}
                  onChange={(e) => setGenerateAnswer(e.target.checked)}
                />
                <div className={`block w-10 h-6 rounded-full transition-colors ${generateAnswer ? "bg-blue-600" : "bg-slate-700"}`}></div>
                <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${generateAnswer ? "translate-x-4" : ""}`}></div>
              </div>
              <span className="text-sm font-medium text-slate-300 flex items-center gap-1.5">
                <BrainCircuit className="w-4 h-4 text-blue-400" />
                Generate Answer
              </span>
            </label>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto pb-8">
        {isSearching ? (
          <div className="mt-12">
            <LoadingSpinner text="Retrieving context and generating response..." />
          </div>
        ) : searchError ? (
          <div className="mt-12">
            <ConnectionErrorState message={searchError} onRetry={() => void handleSearch()} />
          </div>
        ) : searchStats ? (
          <div className="space-y-6">
            {/* Stats Bar */}
            <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-800 text-sm">
              <div className="flex items-center gap-6">
                <span className="text-slate-400">Found <strong className="text-slate-200">{results.length}</strong> sources</span>
                <span className="flex items-center gap-1.5 text-slate-400">
                  <Zap className="w-4 h-4 text-amber-400" />
                  Search: <strong className="text-slate-200">{searchStats.searchTime.toFixed(0)}ms</strong>
                </span>
                <span className="text-slate-400">
                  Total: <strong className="text-slate-200">{searchStats.totalTime.toFixed(0)}ms</strong>
                </span>
                <span className="text-slate-400">
                  Engine: <strong className="text-slate-200">{searchStats.rustUsed ? "Rust hybrid" : "Python"}</strong>
                </span>
              </div>
              
              <button
                onClick={handleGenerateReport}
                disabled={isDownloading}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-50"
              >
                <FileBox className="w-4 h-4" />
                {isDownloading ? "Generating PDF..." : "Export Audit PDF"}
              </button>
            </div>

            {/* Answer Block */}
            {answer && (
              <div className="p-6 rounded-xl bg-gradient-to-br from-blue-900/20 to-slate-900 border border-blue-500/30 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-4 opacity-5">
                  <BrainCircuit className="w-24 h-24" />
                </div>
                <h3 className="flex items-center gap-2 font-medium text-blue-400 mb-4 relative z-10">
                  <BrainCircuit className="w-5 h-5" /> Synthesized Answer
                </h3>
                <div className="text-slate-200 leading-relaxed relative z-10 whitespace-pre-wrap">
                  {answer}
                </div>
              </div>
            )}

            {/* Results List */}
            <div className="space-y-4">
              <h3 className="font-medium text-slate-400 px-1">Semantic Evidence</h3>
              {results.length > 0 ? (
                results.map((result, i) => (
                  <SearchResult key={result.id || i} result={result} />
                ))
              ) : (
                <div className="p-8 text-center text-slate-500 rounded-xl border border-dashed border-slate-800 bg-slate-900/30">
                  No documents met the similarity threshold.
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="mt-12">
            <EmptyState 
              icon={SearchIcon}
              title="Ready to search"
              description="Enter a query above to search through your ingested documents. You can adjust the parameters using the controls below the search bar."
            />
          </div>
        )}
      </div>
    </div>
  );
}
