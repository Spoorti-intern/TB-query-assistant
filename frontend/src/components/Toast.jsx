import { useEffect, useState, useCallback } from "react";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";

let toastId = 0;
let addToastExternal = null;

export function toast(message, type = "info") {
  if (addToastExternal) {
    addToastExternal({ id: ++toastId, message, type });
  }
}

toast.success = (msg) => toast(msg, "success");
toast.error = (msg) => toast(msg, "error");
toast.info = (msg) => toast(msg, "info");

const icons = {
  success: <CheckCircle size={16} />,
  error: <AlertCircle size={16} />,
  info: <Info size={16} />,
};

const colors = {
  success: { bg: "#122b1f", border: "#1a5c35", text: "#5cdda3" },
  error: { bg: "#2b1219", border: "#5c1a2a", text: "#ff8f9b" },
  info: { bg: "#121f2b", border: "#1a355c", text: "#8fb5ff" },
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((t) => {
    setToasts((prev) => [...prev, t]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== t.id));
    }, 4000);
  }, []);

  useEffect(() => {
    addToastExternal = addToast;
    return () => { addToastExternal = null; };
  }, [addToast]);

  const dismiss = (id) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  };

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 16,
        right: 16,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        maxWidth: 380,
      }}
    >
      {toasts.map((t) => {
        const c = colors[t.type] || colors.info;
        return (
          <div
            key={t.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "12px 16px",
              background: c.bg,
              border: `1px solid ${c.border}`,
              borderRadius: 10,
              color: c.text,
              fontSize: 13,
              animation: "fadeIn 0.2s ease",
            }}
          >
            {icons[t.type]}
            <span style={{ flex: 1 }}>{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              style={{
                background: "none",
                border: "none",
                color: c.text,
                cursor: "pointer",
                padding: 2,
              }}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
