"use client";

import { ReactNode, useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

export default function ErrorBoundary({ children, fallback }: ErrorBoundaryProps) {
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // Global error handler
    const handleError = (event: ErrorEvent) => {
      console.error("[ErrorBoundary] Uncaught error:", event.error);
      setError(event.error);
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      console.error("[ErrorBoundary] Unhandled rejection:", event.reason);
      setError(new Error(String(event.reason)));
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);

    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, []);

  const reset = () => {
    setError(null);
    window.location.href = "/";
  };

  if (error) {
    return (
      fallback?.(error, reset) || (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
          <div className="max-w-md w-full">
            <div className="bg-red-950 border border-red-700 rounded-lg p-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-6 h-6 text-red-400 shrink-0 mt-1" />
                <div>
                  <h1 className="text-lg font-bold text-red-400 mb-2">
                    Application Error
                  </h1>
                  <p className="text-sm text-red-300/80 mb-4">
                    {error.message || "An unexpected error occurred"}
                  </p>
                  <button
                    onClick={reset}
                    className="w-full bg-red-600 hover:bg-red-700 text-white font-medium py-2 rounded transition"
                  >
                    Reload Application
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )
    );
  }

  return children;
}
