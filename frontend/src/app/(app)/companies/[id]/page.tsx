"use client";
import { use } from "react";
import Link from "next/link";
import useSWR from "swr";
import { CheckCircle2, CircleSlash, ExternalLink, Info } from "lucide-react";
import { date, n, pct } from "@/lib/format";
import { SOURCE_NAME, TRANSPARENCY } from "@/lib/labels";
import { CategoryBadge, ErrorBox, Loading, QualityBadge } from "@/components/common";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function CompanyDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: c, error } = useSWR(`/companies/${id}`);
  if (error) return <ErrorBox error={error} />;
  if (!c) return <Loading />;
  const t = c.transparency || {};
  const website = c.website ? (c.website.startsWith("http") ? c.website : `https://${c.website}`) : null;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl"><bdi>{c.name}</bdi></h1>
        <p className="mt-1 text-sm text-muted-foreground">{[c.industry, c.size, c.city].filter(Boolean).join(" · ") || "اطلاعات تکمیلی منتشر نشده"}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>درباره شرکت (طبق منابع)</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="prose-auto leading-7" dir="auto">{c.description || "توضیحی منتشر نشده است."}</p>
            {website && <a className="inline-flex items-center gap-1 text-primary hover:underline ltr" href={website} target="_blank" rel="noopener noreferrer nofollow"><ExternalLink className="h-3.5 w-3.5" />{c.website}</a>}
            <div className="text-xs text-muted-foreground">
              پروفایل در منابع: {(c.profiles || []).map((p: any) => (
                <a key={p.source} href={p.url} target="_blank" rel="noopener noreferrer nofollow" className="ms-2 text-primary hover:underline">{SOURCE_NAME[p.source] || p.source}</a>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>شفافیت اطلاعات: {TRANSPARENCY[c.transparency_level]}{c.transparency_score !== null ? ` (${n(c.transparency_score)}/۱۰۰)` : ""}</CardTitle>
            <CardDescription>اطمینان {pct(t.confidence)} · ارزیابی {date(c.assessed_at)}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(t.items || []).map((i: any) => (
              <div key={i.key} className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  {i.present ? <CheckCircle2 className="h-4 w-4 text-[var(--status-good)]" aria-label="دارد" /> : <CircleSlash className="h-4 w-4 text-muted-foreground" aria-label="ندارد" />}
                  {i.label}
                </span>
                <span className="num text-xs text-muted-foreground">{n(i.points)}/{n(i.max)}</span>
              </div>
            ))}
            <p className="flex gap-1 pt-2 text-xs text-muted-foreground"><Info className="h-3.5 w-3.5 shrink-0" />{t.note}</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>آگهی‌های این شرکت</CardTitle><CardDescription>{n(c.jobs.length)} آگهی ثبت‌شده</CardDescription></CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>عنوان</TH><TH>دسته</TH><TH>کیفیت</TH><TH>وضعیت</TH><TH>اولین مشاهده</TH></TR></THead>
            <TBody>
              {c.jobs.map((j: any) => (
                <TR key={j.id}>
                  <TD><Link className="hover:underline" href={`/jobs/${j.id}`}><bdi>{j.title}</bdi></Link></TD>
                  <TD><div className="flex flex-wrap gap-1">{j.categories.map((x: any) => <CategoryBadge key={x.category} category={x.category} sub={x.subcategory} />)}</div></TD>
                  <TD><QualityBadge score={j.quality_score} /></TD>
                  <TD className="text-xs">{j.status === "active" ? "فعال" : "منقضی"}</TD>
                  <TD className="text-xs">{date(j.first_seen_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
