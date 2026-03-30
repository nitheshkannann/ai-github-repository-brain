import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "react-hot-toast";
import ErrorBoundary from "@/components/ErrorBoundary";

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Repo Brain — AI-Powered Code Analysis",
  description:
    "Ask questions about any codebase using AI-powered keyword search and Gemini LLM. Analyse GitHub repos in seconds.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        {/* Inter font via Google CDN for body text */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className={`${jetbrainsMono.variable} antialiased`}>
        <ErrorBoundary>
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: "rgba(5, 18, 40, 0.95)",
                border: "1px solid rgba(0, 212, 255, 0.15)",
                color: "#e2eeff",
                backdropFilter: "blur(20px)",
                borderRadius: "12px",
                fontFamily: "Inter, sans-serif",
                fontSize: "13px",
                boxShadow: "0 0 40px rgba(0, 212, 255, 0.08), 0 8px 32px rgba(0,0,0,0.5)",
              },
              success: {
                iconTheme: { primary: "#00ff9d", secondary: "#051228" },
              },
              error: {
                iconTheme: { primary: "#f87171", secondary: "#051228" },
              },
              loading: {
                iconTheme: { primary: "#00d4ff", secondary: "#051228" },
              },
            }}
          />
          {children}
        </ErrorBoundary>
      </body>
    </html>
  );
}
