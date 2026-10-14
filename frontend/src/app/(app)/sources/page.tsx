"use client";
import { useState } from "react";
import useSWR from "swr";
import { Play } from "lucide-react";
import { api, errorText, qs } from "@/lib/api";
import { ago, dateTime, n } from "@/lib/format";
import { SOURCE_NAME } from "@/lib/labels";
import { useMe } from "@/components/app-shell";
import { ErrorBox, Loading, PageHeader, SourceStatus, Spinner } from "@/components/common";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function SourceAdmin({ s, onChange }: { s: any; onChange: () => void }) {
  const [enabled, setEnabled] = useState<boolean>(s.enabled);
  const [interval, setInterval] = useState<number>(s.interval_minutes);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api(`/admin/sources/${s.key}`, { method: "PUT", json: { enabled, interval_minutes: interval } });
      toast.ok("ذخیره شد");
      onChange();
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function run() {
    try {
      await api("/admin/collection/run", { method: "POST", json: { source: s.key } });
      toast.ok("جمع‌آوری در صف قرار گرفت. پیشرفت در جدول اجراها دیده می‌شود.");
      setTimeout(onChange, 4000);
    } catch (e) {
      toast.error(errorText(e));
    }
  }
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-md bg-muted/50 p-3">
      <label className="flex items-center gap-2 text-sm"><Switch checked={enabled} onCheckedChange={setEnabled} />فعال</label>
      <div className="space-y-1">
        <Label htmlFor={`iv-${s.key}`} className="text-xs">فاصله بررسی (دقیقه، حداقل {n(s.min_interval_minutes)})</Label>
        <Input id={`iv-${s.key}`} type="number" className="w-32" min={s.min_interval_minutes} value={interval}
          onChange={(e) => setInterval(Number(e.target.value))} />
      </div>
      <Button size="sm" variant="outline" onClick={save} disabled={busy}>{busy && <Spinner />}ذخیره</Button>
      <Button size="sm" onClick={run} disabled={!s.enabled}><Play />اجرای اکنون</Button>
    </div>
  );
}

export default function SourcesPage() {
  const { data, error, mutate } = useSWR("/sources/health", { refreshInterval: 30_000 });
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const { data: runs } = useSWR(isAdmin ? `/admin/collection/runs${qs({})}` : null, { refreshInterval: 30_000 });
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={3} />;

  return (
    <div className="space-y-4">
      <PageHeader title="منابع و پوشش داده"
        description="روش مجاز دسترسی، محدودیت‌ها و پوشش واقعی هر منبع. ادعای دریافت همه آگهی‌ها مطرح نمی‌شود؛ پوشش هر اجرا جداگانه گزارش شده است." />
      {data.sources.map((s: any) => (
        <Card key={s.key}>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle><bdi>{s.name}</bdi> <a className="ms-1 text-xs font-normal text-primary ltr" href={s.base_url} target="_blank" rel="noopener noreferrer">{s.base_url}</a></CardTitle>
              <SourceStatus status={s.status} running={s.running} />
            </div>
            <CardDescription>
              آخرین اجرا {ago(s.last_run_at)} · آخرین دریافت موفق {ago(s.last_success_at)} · اجرای بعدی {dateTime(s.next_run_at)}
              {!s.baseline_done && " · اجرای اولیه هنوز انجام نشده (در آن اعلانی ارسال نمی‌شود)"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">کل آگهی‌های ذخیره‌شده</div><div className="num font-semibold">{n(s.jobs_total)}</div></div>
              <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">مرتبط</div><div className="num font-semibold">{n(s.jobs_relevant)}</div></div>
              <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">مرتبط فعال</div><div className="num font-semibold">{n(s.jobs_relevant_active)}</div></div>
              <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">فاصله بررسی</div><div className="num font-semibold">{n(s.interval_minutes)} دقیقه</div></div>
            </div>
            <div><span className="font-medium">روش دسترسی: </span><span className="prose-auto ltr text-muted-foreground" dir="ltr">{s.access_method}</span></div>
            <div><span className="font-medium">محدودیت‌ها و پوشش: </span><span className="prose-auto text-muted-foreground" dir="ltr">{s.limitations}</span></div>
            {s.coverage_note && <div><span className="font-medium">پوشش آخرین اجرا: </span><span className="text-muted-foreground" dir="ltr">{s.coverage_note}</span></div>}
            <div className="text-xs text-muted-foreground">robots.txt آخرین بار {dateTime(s.robots_checked_at)} بررسی شد.</div>
            {s.last_error && <div className="rounded-md border border-[var(--status-warning)]/50 p-2 text-xs prose-auto" dir="ltr">{s.last_error}</div>}
            {isAdmin && <SourceAdmin s={s} onChange={() => mutate()} />}
          </CardContent>
        </Card>
      ))}
      {isAdmin && runs && (
        <Card>
          <CardHeader><CardTitle>تاریخچه اجراها و خطاها</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <THead><TR><TH>منبع</TH><TH>شروع</TH><TH>وضعیت</TH><TH>یافته</TH><TH>دریافت</TH><TH>جدید/تغییر/منقضی</TH><TH>خطا</TH><TH>HTTP</TH><TH>جزئیات</TH></TR></THead>
              <TBody>
                {runs.items.map((r: any) => (
                  <TR key={r.id}>
                    <TD>{SOURCE_NAME[r.source]}</TD>
                    <TD className="whitespace-nowrap text-xs">{dateTime(r.started_at)}<div className="text-muted-foreground">{r.trigger === "manual" ? "دستی" : "زمان‌بندی"}</div></TD>
                    <TD><Badge variant={r.status === "success" ? "good" : r.status === "partial" ? "warning" : r.status === "running" ? "default" : "critical"}>{r.status}</Badge></TD>
                    <TD className="num">{n(r.discovered)}</TD>
                    <TD className="num">{n(r.fetched)}</TD>
                    <TD className="num">{n(r.new_jobs)} / {n(r.changed_jobs)} / {n(r.expired_jobs)}</TD>
                    <TD className="num">{n(r.failed)}</TD>
                    <TD className="text-xs ltr">{Object.entries(r.http_status_counts || {}).map(([k, v]) => `${k}:${v}`).join(" ")}</TD>
                    <TD>
                      {(r.errors?.length > 0 || r.coverage_note) && (
                        <details className="max-w-md text-xs">
                          <summary className="cursor-pointer">نمایش</summary>
                          {r.coverage_note && <p className="mt-1" dir="ltr">{r.coverage_note}</p>}
                          <ul className="mt-1 list-disc ps-4" dir="ltr">{r.errors.map((e: string, i: number) => <li key={i} className="break-all">{e}</li>)}</ul>
                        </details>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
