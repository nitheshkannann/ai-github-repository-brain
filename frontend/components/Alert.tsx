"use client";

import { AlertTriangle, X } from "lucide-react";
import { useEffect, useState } from "react";

interface AlertProps {
    type?: "error" | "warning" | "info";
    message: string;
    onClose?: () => void;
    autoClose?: boolean;
}

export default function Alert({ type = "error", message, onClose, autoClose = true }: AlertProps) {
    const [visible, setVisible] = useState(true);

    useEffect(() => {
        if (autoClose) {
            const timer = setTimeout(() => {
                setVisible(false);
                onClose?.();
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [autoClose, onClose]);

    if (!visible) return null;

    const colors = {
        error: "bg-red-900/20 border-red-500/30 text-red-300",
        warning: "bg-amber-900/20 border-amber-500/30 text-amber-300",
        info: "bg-blue-900/20 border-blue-500/30 text-blue-300",
    };

    const iconColors = {
        error: "text-red-400",
        warning: "text-amber-400",
        info: "text-blue-400",
    };

    return (
        <div className={`flex items-center gap-3 p-3 rounded-lg border ${colors[type]} animate-fade-in`}>
            <AlertTriangle size={16} className={iconColors[type]} />
            <span className="text-sm flex-1">{message}</span>
            {onClose && (
                <button
                    onClick={() => {
                        setVisible(false);
                        onClose();
                    }}
                    className={`p-1 rounded hover:bg-white/5 transition-colors ${iconColors[type]}`}
                >
                    <X size={14} />
                </button>
            )}
        </div>
    );
}
