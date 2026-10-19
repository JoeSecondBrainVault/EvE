import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "E.V.E. — Extensible Virtual Entity",
  description: "Personal AI Study & Work Assistant for Lectures, Transcripts, Obsidian Notes, and Coursework",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 flex h-screen overflow-hidden antialiased">
        <Navbar />
        <main className="flex-1 flex flex-col h-screen overflow-y-auto bg-slate-950">
          {children}
        </main>
      </body>
    </html>
  );
}
