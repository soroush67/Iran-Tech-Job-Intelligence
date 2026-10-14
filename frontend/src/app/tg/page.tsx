"use client";
/* Telegram Mini App. Login = Telegram initData, validated by the backend (HMAC with the
   bot token); only Telegram accounts linked to a site user get a session. */
import { useEffect, useState } from "react";
import Script from "next/script";
import { ExternalLink } from "lucide-react";
import { api, errorText, qs } from "@/lib/api";
import { ago, salaryRange } from "@/lib/format";
import { CATEGORY_LABEL, SALARY_STATUS, WORK_MODE } from "@/lib/labels";
import { CategoryBadge, Empty, Loading } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

declare global {
  interface Window { Telegram?: { WebApp: any } }
}

const TABS = [{ key: "", label: "همه" }, ...Object.entries(CATEGORY_LABEL).map(([key, label]) => ({ key, label }))];

export default function MiniApp() {
  const [state, setState] = useState<"loading" | "ready" | "error" | "outside">("loading");
  const [err, setErr] = useState("");
  const [cat, setCat] = useState("");
  const [jobs, setJobs] = useState<any[] | null>(null);
  const [scriptReady, setScriptReady] = useState(false);

  useEffect(() => {
    if (!scriptReady) return;
    const wa = window.Telegram?.WebApp;
    if (!wa || !wa.initData) {
      setState("outside");
      return;
    }
    wa.ready();
    wa.expand();
    document.documentElement.classList.toggle("dark", wa.colorScheme === "dark");
    api("/telegram/webapp/auth", { method: "POST", json: { init_data: wa.initData } })
      .then(() => setState("ready"))
      .catch((e) => { setErr(errorText(e)); setState("error"); });
  }, [scriptReady]);

  useEffect(() => {
    if (state !== "ready") return;
    setJobs(null);
    api(`/jobs${qs({ categories: cat || undefined, page_size: 20 })}`).then((r) => setJobs(r.items)).catch((e) => setErr(errorText(e)));
  }, [state, cat]);

  return (
    <div className="mx-auto max-w-lg p-3">
      <Script src="https://telegram.org/js/telegram-web-app.js" strategy="afterInteractive" onReady={() => setScriptReady(true)} onError={() => setState("outside")} />
      <h1 className="mb-3 text-lg font-bold">Iran Tech Jobs</h1>
      {state === "loading" && <Loading rows={3} />}
      {state === "outside" && <Empty>این صفحه باید از داخل ربات تلگرام باز شود. <a className="text-primary underline" href="/">نسخه وب</a></Empty>}
      {state === "error" && <Empty><span className="prose-auto">{err}</span></Empty>}
      {state === "ready" && (
        <>
          <div className="mb-3 flex gap-1 overflow-x-auto pb-1">
            {TABS.map((t) => (
              <Button key={t.key} size="sm" variant={cat === t.key ? "default" : "outline"} onClick={() => setCat(t.key)}>
                <bdi className="ltr">{t.label}</bdi>
              </Button>
            ))}
          </div>
          {!jobs ? <Loading rows={4} /> : jobs.length === 0 ? <Empty>آگهی فعالی نیست.</Empty> : (
            <ul className="space-y-2">
              {jobs.map((j) => (
                <li key={j.id} className="rounded-lg border bg-card p-3">
                  <a href={`/jobs/${j.id}`} className="font-medium"><bdi>{j.title}</bdi></a>
                  <div className="text-xs text-muted-foreground">
                    <bdi>{j.company_name || "شرکت نامشخص"}</bdi> · {[j.city, j.work_mode && WORK_MODE[j.work_mode]].filter(Boolean).join(" · ")} · {ago(j.published_at || j.first_seen_at)}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {j.categories.slice(0, 2).map((c: any) => <CategoryBadge key={c.category} category={c.category} sub={c.subcategory} />)}
                    <Badge variant="secondary">{SALARY_STATUS[j.salary_status]}{j.salary_status !== "unknown" ? `: ${salaryRange(j.salary_min, j.salary_max)}` : ""}</Badge>
                  </div>
                  <a href={j.canonical_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-primary">
                    <ExternalLink className="h-3 w-3" />آگهی اصلی
                  </a>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
