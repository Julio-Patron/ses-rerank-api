import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { ToastProvider } from "@/components/Toast";

export const metadata: Metadata = {
  title: "SES Enterprise Gateway | Developer Portal",
  description: "Manage your RAG engine, documents, and analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0a0e1a] text-slate-200 antialiased min-h-screen flex selection:bg-blue-500/30 selection:text-blue-200">
        <ToastProvider>
          <Sidebar />
          <main className="flex-1 flex flex-col min-w-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-900/10 via-[#0a0e1a] to-[#0a0e1a]">
            {children}
          </main>
        </ToastProvider>
      </body>
    </html>
  );
}
