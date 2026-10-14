"use client";
import { use, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { AlertTriangle, ExternalLink, Info, RefreshCw, Sparkles } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { date, dateTime, n, pct, salaryRange } from "@/lib/format";
import { EMPLOYMENT, EVENT, SENIORITY, SOURCE_NAME, WORK_MODE } from "@/lib/labels";
import { useMe } from "@/components/app-shell";
import { CategoryBadge, ErrorBox, Loading, QualityBadge, SalaryBadge } from "@/components/common";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-end">{v}</span>
    </div>
  );
}

function Meter({ score, max }: { score: number; max: number }) {
  return (
    <div className="h-2 w-full rounded bg-muted" role="meter" aria-valuenow={score} aria-valuemax={max} aria-valuemin={0}>
      <div className="h-2 rounded bg-[var(--series-1)]" style={{ width: `${(score / max) * 100}%` }} />
    </div>
  );
}

function EventDiff({ e }: { e: any }) {
  const d = e.diff || {};
  if (e.type === "SALARY_CHANGED")
    return <span><bdi>{d.salary_original?.old || "—"}</bdi> ← <bdi>{d.salary_original?.new || "—"}</bdi></span>;
  if (e.type === "REQUIREMENTS_CHANGED")
    return (
      <span className="ltr text-xs">
        {d.required_skills?.added?.length ? `+ ${d.required_skills.added.join(", ")} ` : ""}
        {d.required_skills?.removed?.length ? `− ${d.required_skills.removed.join(", ")}` : ""}
        {d.experience_required?.old !== d.experience_required?.new ? ` exp: ${d.experience_required?.old || "—"} → ${d.experience_required?.new || "—"}` : ""}
      </span>
    );
  if (e.type === "WORK_MODE_CHANGED")
    return <span>{WORK_MODE[d.work_mode?.old] || "—"} ← {WORK_MODE[d.work_mode?.new] || "—"}</span>;
  if (e.type === "DESCRIPTION_CHANGED")
    return (
      <details>
        <summary className="cursor-pointer text-xs">شباهت با نسخه قبل: {pct(d.similarity)} — مشاهده تفاوت</summary>
        <pre className="mt-2 max-h-60 overflow-auto rounded bg-muted p-2 text-xs prose-auto" dir="auto">{(d.diff || []).join("\n")}</pre>
      </details>
    );
  if (e.type === "JOB_EXPIRED") return <span className="text-xs">{d.reason}</span>;
  return null;
}

export default function JobDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: j, error, mutate } = useSWR(`/jobs/${id}`);
  const { data: me } = useMe();
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorBox error={error} />;
  if (!j) return <Loading rows={5} />;
  const a = j.analysis;
  const est = j.salary_estimate || {};

  async function reanalyze() {
    setBusy(true);
    try {
      await api(`/admin/ai/reanalyze/${id}`, { method: "POST" });
      toast.ok("در صف تحلیل قرار گرفت؛ چند لحظه بعد صفحه را تازه کنید.");
      setTimeout(() => mutate(), 8000);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl"><bdi>{j.title}</bdi></h1>
          <div className="mt-1 text-sm text-muted-foreground">
            {j.company_id ? <Link className="hover:underline" href={`/companies/${j.company_id}`}><bdi>{j.company_name}</bdi></Link> : <bdi>{j.company_name || "شرکت نامشخص"}</bdi>}
            {" · "}{[j.province, j.city].filter(Boolean).join(" / ") || "محل نامشخص"} · {SOURCE_NAME[j.source]}
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {j.categories.map((c: any) => <CategoryBadge key={c.category} category={c.category} sub={c.subcategory} />)}
            {j.status === "expired" && <Badge variant="secondary">منقضی</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <a href={j.canonical_url} target="_blank" rel="noopener noreferrer nofollow"><ExternalLink />آگهی اصلی</a>
          </Button>
          {me?.role === "admin" && (
            <Button variant="outline" onClick={reanalyze} disabled={busy}><RefreshCw />تحلیل مجدد</Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader><CardTitle>شرح آگهی</CardTitle></CardHeader>
            <CardContent>
              <div className="prose-auto text-sm leading-7" dir="auto">{j.description || "—"}</div>
              {j.benefits?.length > 0 && (
                <div className="mt-4">
                  <div className="mb-1 text-sm font-medium">مزایا</div>
                  <div className="flex flex-wrap gap-1">{j.benefits.map((b: string) => <Badge key={b} variant="secondary"><bdi>{b}</bdi></Badge>)}</div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4" />تحلیل</CardTitle>
              <CardDescription>
                {a ? <>موتور: <bdi className="ltr">{a.engine}{a.model ? ` (${a.model})` : ""}</bdi> · {dateTime(a.created_at)}</> : "هنوز تحلیل نشده"}
              </CardDescription>
            </CardHeader>
            {a && (
              <CardContent className="space-y-5">
                {a.error && (
                  <div className="flex gap-2 rounded-md border border-[var(--status-warning)]/50 p-2 text-xs">
                    <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--status-warning)]" />
                    <span className="prose-auto">تحلیل مدل انجام نشد و تحلیل قاعده‌محور نمایش داده می‌شود: {a.error}</span>
                  </div>
                )}
                <p className="text-sm prose-auto">{a.summary_fa}</p>
                <section>
                  <h4 className="mb-2 text-sm font-semibold">دسته‌بندی و شواهد</h4>
                  {a.categories.length === 0 ? <p className="text-sm text-muted-foreground">در دسته‌های هدف قرار نگرفت.</p> : (
                    <ul className="space-y-2">
                      {a.categories.map((c: any) => (
                        <li key={c.category} className="rounded-md border p-2 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <CategoryBadge category={c.category} sub={c.subcategory} />
                            <span className="text-xs text-muted-foreground">اطمینان {pct(c.confidence)}</span>
                          </div>
                          <ul className="mt-1 list-disc ps-5 text-xs text-muted-foreground">{c.evidence.map((e: string, i: number) => <li key={i} className="prose-auto">{e}</li>)}</ul>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <section>
                  <h4 className="mb-2 text-sm font-semibold">سطح ارشدیت</h4>
                  <div className="text-sm">
                    <bdi className="ltr font-medium">{SENIORITY[a.seniority.level]}</bdi>
                    <span className="ms-2 text-xs text-muted-foreground">اطمینان {pct(a.seniority.confidence)}</span>
                  </div>
                  {a.seniority.evidence?.length > 0 && <ul className="mt-1 list-disc ps-5 text-xs text-muted-foreground">{a.seniority.evidence.map((e: string, i: number) => <li key={i} className="prose-auto">{e}</li>)}</ul>}
                </section>
                <section>
                  <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">کیفیت آگهی <QualityBadge score={a.quality.total} /></h4>
                  <div className="space-y-2">
                    {a.quality.criteria.map((c: any) => (
                      <div key={c.key}>
                        <div className="flex justify-between text-xs"><span>{c.label}</span><span className="num">{n(c.score)} / {n(c.max)}</span></div>
                        <Meter score={c.score} max={c.max} />
                        <div className="mt-0.5 text-xs text-muted-foreground prose-auto">{c.reason}</div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 flex gap-1 text-xs text-muted-foreground"><Info className="h-3.5 w-3.5 shrink-0" />{a.quality.note}</p>
                </section>
                <section>
                  <h4 className="mb-2 text-sm font-semibold">هشدارهای احتمالی</h4>
                  {a.red_flags.length === 0 ? <p className="text-sm text-muted-foreground">موردی دیده نشد.</p> : (
                    <ul className="space-y-1.5">
                      {a.red_flags.map((f: any) => (
                        <li key={f.code} className="flex gap-2 text-sm">
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-warning)]" aria-label="هشدار" />
                          <span>{f.message}{f.evidence && <span className="block text-xs text-muted-foreground prose-auto">{f.evidence}</span>}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">{a.disclaimer}</p>
                </section>
                {a.llm_notes?.length > 0 && (
                  <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer">یادداشت‌های اعتبارسنجی خروجی مدل</summary>
                    <ul className="mt-1 list-disc ps-5">{a.llm_notes.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
                  </details>
                )}
              </CardContent>
            )}
          </Card>

          <Card>
            <CardHeader><CardTitle>تاریخچه تغییرات</CardTitle><CardDescription>{n(j.history.length)} نسخه ذخیره‌شده</CardDescription></CardHeader>
            <CardContent>
              {j.events.length === 0 ? <p className="text-sm text-muted-foreground">رویدادی ثبت نشده.</p> : (
                <ol className="space-y-3 border-s ps-4">
                  {j.events.map((e: any) => (
                    <li key={e.id} className="text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={e.type === "JOB_EXPIRED" ? "secondary" : "default"}>{EVENT[e.type] || e.type}</Badge>
                        <span className="text-xs text-muted-foreground">{dateTime(e.created_at)}</span>
                        {e.is_baseline && <Badge variant="outline" title="ثبت در اجرای اولیه؛ اعلان ارسال نشد">اجرای اولیه</Badge>}
                      </div>
                      <div className="mt-1"><EventDiff e={e} /></div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>مشخصات</CardTitle></CardHeader>
            <CardContent>
              <Row k="شیوه همکاری" v={j.work_mode ? WORK_MODE[j.work_mode] : "نامشخص"} />
              <Row k="نوع قرارداد" v={EMPLOYMENT[j.employment_type] || "نامشخص"} />
              <Row k="سابقه" v={<bdi>{j.experience_required || "—"}</bdi>} />
              <Row k="سطح" v={<bdi className="ltr">{SENIORITY[j.seniority]}</bdi>} />
              <Row k="تاریخ انتشار" v={j.published_at ? date(j.published_at) : <span title={j.published_at_note}>نامشخص در منبع</span>} />
              <Row k="اولین مشاهده" v={dateTime(j.first_seen_at)} />
              <Row k="آخرین مشاهده" v={dateTime(j.last_seen_at)} />
              <Row k="آخرین تغییر" v={dateTime(j.last_changed_at)} />
              {j.expires_at && <Row k="انقضا (طبق منبع)" v={date(j.expires_at)} />}
              {j.published_at_note && <p className="mt-2 text-xs text-muted-foreground">{j.published_at_note}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2">حقوق <SalaryBadge status={j.salary_status} /></CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">
              {j.salary_status === "reported" && (
                <>
                  <div className="num text-lg font-semibold">{salaryRange(est.min, est.max)}</div>
                  <div className="text-xs text-muted-foreground">متن آگهی: <bdi>{j.salary_original}</bdi></div>
                </>
              )}
              {j.salary_status === "estimated" && (
                <>
                  <div className="num text-lg font-semibold">{salaryRange(est.min, est.max)}</div>
                  {est.median && <div className="text-xs">میانه: <span className="num">{salaryRange(est.median, est.median)}</span></div>}
                  <Row k="روش" v={est.method === "benchmark_dataset" ? "دیتاست معیار حقوق" : "حقوق‌های اعلام‌شده آگهی‌های مشابه"} />
                  <Row k="منبع" v={<bdi>{est.source}{est.dataset ? ` (${est.dataset})` : ""}</bdi>} />
                  <Row k="سال داده" v={n(est.data_year)} />
                  <Row k="تعداد نمونه" v={n(est.sample_size)} />
                  <Row k="اطمینان" v={pct(est.confidence)} />
                </>
              )}
              {j.salary_status === "unknown" && (
                <>
                  {j.salary_original && <div>متن آگهی: <bdi>{j.salary_original}</bdi></div>}
                  <p className="text-muted-foreground">{est.reason}</p>
                  <p className="text-xs text-muted-foreground">{est.note}</p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>مهارت‌ها</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="mb-1 text-xs text-muted-foreground">ضروری</div>
                <div className="flex flex-wrap gap-1">{j.skills.filter((s: any) => s.type === "required").map((s: any) => <Badge key={s.name} variant="outline" className="ltr" title={`منشأ: ${s.origin}`}>{s.name}</Badge>)}</div>
              </div>
              {j.skills.some((s: any) => s.type === "optional") && (
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">ترجیحی</div>
                  <div className="flex flex-wrap gap-1">{j.skills.filter((s: any) => s.type === "optional").map((s: any) => <Badge key={s.name} variant="secondary" className="ltr">{s.name}</Badge>)}</div>
                </div>
              )}
            </CardContent>
          </Card>

          {j.match && (
            <Card>
              <CardHeader><CardTitle>تطابق با پروفایل شما: <span className="num">{n(j.match.match_score)}٪</span></CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {j.match.breakdown.map((p: any) => (
                  <div key={p.key}>
                    <div className="flex justify-between text-xs"><span>{p.label}</span><span className="num">{n(Math.round(p.score))} / {n(p.max)}</span></div>
                    <Meter score={p.score} max={p.max} />
                    <div className="text-xs text-muted-foreground"><bdi>{p.detail}</bdi>{p.missing?.length ? <> — کم: <bdi className="ltr">{p.missing.join(", ")}</bdi></> : null}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {j.duplicates.length > 0 && (
            <Card>
              <CardHeader><CardTitle>همین آگهی در منابع دیگر</CardTitle><CardDescription>اطلاعات منبع اصلی هر کدام حفظ شده است</CardDescription></CardHeader>
              <CardContent className="space-y-1 text-sm">
                {j.duplicates.map((d: any) => (
                  <div key={d.id}><Link href={`/jobs/${d.id}`} className="hover:underline"><bdi>{d.title}</bdi></Link> · {SOURCE_NAME[d.source]}</div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
