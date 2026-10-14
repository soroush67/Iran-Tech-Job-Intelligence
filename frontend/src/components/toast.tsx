"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

type Toast = { id: number; text: string; kind: "ok" | "error" };
let push: ((t: Omit<Toast, "id">) => void) | null = null;

export const toast = {
  ok: (text: string) => push?.({ text, kind: "ok" }),
  error: (text: string) => push?.({ text, kind: "error" }),
};

export function ToastHost() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    push = (t) => {
      const id = Date.now() + Math.random();
      setItems((x) => [...x, { ...t, id }]);
      setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 5000);
    };
    return () => {
      push = null;
    };
  }, []);
  return (
    <div className="fixed bottom-4 left-4 z-[60] flex max-w-sm flex-col gap-2" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className="flex items-start gap-2 rounded-lg border bg-card p-3 text-sm shadow-lg">
          {t.kind === "ok" ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-good)]" />
          ) : (
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-critical)]" />
          )}
          <span className="prose-auto">{t.text}</span>
        </div>
      ))}
    </div>
  );
}
