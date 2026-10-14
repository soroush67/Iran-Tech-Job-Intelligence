"use client";
import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { qs } from "@/lib/api";
import { n } from "@/lib/format";
import { SOURCE_NAME, TRANSPARENCY } from "@/lib/labels";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function TransparencyBadge({ level, score }: { level: string; score?: number | null }) {
  const v = level === "high" ? "good" : level === "medium" ? "default" : level === "low" ? "warning" : "secondary";
  return <Badge variant={v as any}>{TRANSPARENCY[level] || level}{score !== null && score !== undefined ? ` · ${n(score)}` : ""}</Badge>;
}

export default function CompaniesPage() {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("jobs");
  const [page, setPage] = useState(1);
  const { data, error } = useSWR(`/companies${qs({ q: q || undefined, sort, page, page_size: 25 })}`, { keepPreviousData: true });
  const pages = data ? Math.max(1, Math.ceil(data.total / 25)) : 1;
  return (
    <div>
      <PageHeader title="شرکت‌ها" description="اطلاعات قابل بررسی کارفرمایانی که آگهی مرتبط دارند و ارزیابی شفافیت آن‌ها" />
      <div className="mb-3 flex flex-wrap gap-2">
        <Input className="max-w-xs" placeholder="نام شرکت" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <div className="w-48">
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger aria-label="مرتب‌سازی"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="jobs">بیشترین آگهی فعال</SelectItem>
              <SelectItem value="transparency">شفافیت</SelectItem>
              <SelectItem value="name">نام</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      {error ? <ErrorBox error={error} /> : !data ? <Loading /> : data.items.length === 0 ? <Empty>شرکتی پیدا نشد.</Empty> : (
        <Card>
          <Table>
            <THead><TR><TH>شرکت</TH><TH>حوزه</TH><TH>اندازه</TH><TH>وب‌سایت</TH><TH>آگهی فعال مرتبط</TH><TH>شفافیت اطلاعات</TH><TH>منابع</TH></TR></THead>
            <TBody>
              {data.items.map((c: any) => (
                <TR key={c.id}>
                  <TD><Link href={`/companies/${c.id}`} className="font-medium hover:underline"><bdi>{c.name}</bdi></Link></TD>
                  <TD className="text-xs">{c.industry || "—"}</TD>
                  <TD className="text-xs"><bdi>{c.size || "—"}</bdi></TD>
                  <TD className="text-xs ltr">{c.website || "—"}</TD>
                  <TD className="num">{n(c.active_jobs)}</TD>
                  <TD><TransparencyBadge level={c.transparency_level} score={c.transparency_score} /></TD>
                  <TD className="text-xs">{c.sources.map((s: string) => SOURCE_NAME[s] || s).join("، ")}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
      {data && data.total > 25 && (
        <div className="mt-3 flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronRight />قبلی</Button>
          <span className="num text-sm">صفحه {n(page)} از {n(pages)}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>بعدی<ChevronLeft /></Button>
        </div>
      )}
    </div>
  );
}
