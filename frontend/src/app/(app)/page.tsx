"use client";
import Link from "next/link";
import useSWR from "swr";
import { CategoryBars } from "@/components/charts";
import { Empty, ErrorBox, Loading, PageHeader, SourceStatus, StatTile } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ago, dateTime, n } from "@/lib/format";
import { CATEGORIES, CATEGORY_COLOR, CATEGORY_LABEL, SALARY_STATUS, SOURCE_NAME } from "@/lib/labels";

const RUN_STATUS: Record<string, string> = {
  success: "موفق", partial: "ناقص", failed: "ناموفق", blocked: "مسدود", running: "در حال اجرا", skipped: "رد شد",
};

export default function DashboardPage() {
  const { data, error, isLoading } = useSWR("/dashboard", { refreshInterval: 60_000 });
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !data) return <Loading rows={4} />;

  const cats = CATEGORIES.map((c) => ({ name: CATEGORY_LABEL[c], value: data.by_category[c] || 0, color: CATEGORY_COLOR[c] }));
  const noData = data.total_relevant === 0;

  return (
    <div className="space-y-5">
      <PageHeader title="داشبورد" description="وضعیت لحظه‌ای آگهی‌های مرتبط و منابع جمع‌آوری" />
      {noData && (
        <Empty>
          هنوز آگهی‌ای جمع‌آوری نشده است. اولین اجرای جمع‌آوری طبق برنامه انجام می‌شود؛ مدیر می‌تواند از
          {" "}<Link className="text-primary underline" href="/sources">منابع و پوشش</Link> آن را دستی اجرا کند.
        </Empty>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="آگهی‌های مرتبط فعال" value={n(data.total_relevant_active)} hint={`کل ثبت‌شده: ${n(data.total_relevant)}`} />
        <StatTile label="جدید در ۲۴ ساعت اخیر" value={n(data.new_24h)}
          hint={data.first_seen_24h !== data.new_24h ? `${n(data.first_seen_24h)} اولین مشاهده (شامل اجرای اولیه)` : undefined} />
        <StatTile label="تغییرکرده در ۲۴ ساعت" value={n(data.changed_24h)} hint={`منقضی‌شده: ${n(data.expired_24h)}`} />
        <StatTile label="حقوق اعلام‌شده" value={n(data.salary_status.reported || 0)}
          hint={`تخمینی: ${n(data.salary_status.estimated || 0)} · نامشخص: ${n(data.salary_status.unknown || 0)}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>توزیع مشاغل فعال</CardTitle>
            <CardDescription>یک آگهی می‌تواند در چند دسته باشد</CardDescription>
          </CardHeader>
          <CardContent><CategoryBars data={cats} /></CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>وضعیت منابع</CardTitle>
            <CardDescription><Link href="/sources" className="text-primary hover:underline">جزئیات پوشش و محدودیت‌ها</Link></CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.sources.map((s: any) => (
              <div key={s.key} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{SOURCE_NAME[s.key] || s.name}</span>
                  <SourceStatus status={s.status} running={s.running} />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1 text-xs text-muted-foreground">
                  <span>آگهی مرتبط فعال: <span className="num text-foreground">{n(s.jobs_relevant_active)}</span></span>
                  <span>آخرین موفق: {ago(s.last_success_at)}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>آخرین اجراهای جمع‌آوری</CardTitle></CardHeader>
        <CardContent>
          {data.last_runs.length === 0 ? <Empty>هنوز اجرایی ثبت نشده است.</Empty> : (
            <Table>
              <THead><TR>
                <TH>منبع</TH><TH>وضعیت</TH><TH>شروع</TH><TH>یافته</TH><TH>دریافت</TH><TH>جدید</TH><TH>تغییر</TH><TH>منقضی</TH><TH>خطا</TH>
              </TR></THead>
              <TBody>
                {data.last_runs.map((r: any) => (
                  <TR key={r.id}>
                    <TD>{SOURCE_NAME[r.source]}</TD>
                    <TD>
                      <Badge variant={r.status === "success" ? "good" : r.status === "partial" ? "warning" : r.status === "running" ? "default" : "critical"}>
                        {RUN_STATUS[r.status] || r.status}
                      </Badge>
                      {r.is_baseline && <Badge variant="secondary" className="ms-1" title="اجرای اولیه: اعلانی ارسال نمی‌شود">پایه</Badge>}
                    </TD>
                    <TD className="whitespace-nowrap text-xs">{dateTime(r.started_at)}</TD>
                    <TD className="num">{n(r.discovered)}</TD>
                    <TD className="num">{n(r.fetched)}</TD>
                    <TD className="num">{n(r.new_jobs)}</TD>
                    <TD className="num">{n(r.changed_jobs)}</TD>
                    <TD className="num">{n(r.expired_jobs)}</TD>
                    <TD className="num">{n(r.failed)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        وضعیت حقوق: {Object.entries(SALARY_STATUS).map(([k, v]) => `${v}`).join(" / ")} — نبودن حقوق در آگهی به معنای پایین بودن آن نیست.
      </p>
    </div>
  );
}
