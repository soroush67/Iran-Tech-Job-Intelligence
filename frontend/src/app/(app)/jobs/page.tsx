"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { ChevronLeft, ChevronRight, Download, ExternalLink, Filter, Save } from "lucide-react";
import { api, errorText, qs } from "@/lib/api";
import { ago, n, salaryRange } from "@/lib/format";
import { SENIORITY, SOURCE_NAME, WORK_MODE } from "@/lib/labels";
import { CategoryBadge, Empty, ErrorBox, Loading, PageHeader, QualityBadge, SalaryBadge, Spinner } from "@/components/common";
import { FilterPanel, Filters, filtersFromSearch, filtersToApi, filtersToParams } from "@/components/job-filters";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const SORT_LABEL: Record<string, string> = {
  newest: "جدیدترین (اولین مشاهده)", published: "تاریخ انتشار", changed: "آخرین تغییر", salary: "حقوق",
  quality: "کیفیت آگهی", title: "عنوان",
};

function useDebounced<T>(value: T, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function JobsExplorer() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearch(new URLSearchParams(sp.toString())));
  const [sort, setSort] = useState(sp.get("sort") || "newest");
  const [page, setPage] = useState(Number(sp.get("page") || 1));
  const [showFilters, setShowFilters] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const debounced = useDebounced(filters);
  const pageSize = 25;

  const params = useMemo(() => ({ ...filtersToParams(debounced), sort, page, page_size: pageSize }), [debounced, sort, page]);
  useEffect(() => {
    router.replace(`${pathname}${qs({ ...filtersToParams(debounced), sort: sort !== "newest" ? sort : undefined, page: page > 1 ? page : undefined })}`, { scroll: false });
  }, [debounced, sort, page, pathname, router]);

  const { data: facets } = useSWR("/jobs/facets");
  const { data, error, isLoading } = useSWR(`/jobs${qs(params)}`, { keepPreviousData: true });
  const pages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  const setF = (f: Filters) => {
    setFilters(f);
    setPage(1);
  };

  return (
    <div>
      <PageHeader
        title="آگهی‌ها"
        description="جست‌وجو و فیلتر ترکیبی آگهی‌های مرتبط؛ صفحه‌بندی و مرتب‌سازی سمت سرور"
        actions={
          <>
            <Button variant="outline" className="lg:hidden" onClick={() => setShowFilters(!showFilters)}><Filter />فیلترها</Button>
            <Button variant="outline" onClick={() => setSaveOpen(true)}><Save />ذخیره فیلتر</Button>
            <Button variant="outline" asChild>
              <a href={`/api/v1/jobs/export.csv${qs({ ...filtersToParams(debounced), sort })}`}><Download />CSV</a>
            </Button>
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <Card className={showFilters ? "" : "hidden lg:block"}>
          <CardContent className="pt-4 sm:pt-5"><FilterPanel f={filters} set={setF} facets={facets} /></CardContent>
        </Card>
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">
              {data ? <>{n(data.total)} آگهی</> : "…"}
              {isLoading && <span className="ms-2 inline-block align-middle"><Spinner /></span>}
            </span>
            <div className="w-56">
              <Select value={sort} onValueChange={(v) => { setSort(v); setPage(1); }}>
                <SelectTrigger aria-label="مرتب‌سازی"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(SORT_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          {error ? <ErrorBox error={error} /> : !data ? <Loading rows={6} /> : data.items.length === 0 ? (
            <Empty>آگهی‌ای با این فیلترها پیدا نشد.</Empty>
          ) : (
            <>
            {/* phones: cards instead of a wide table */}
            <ul className="space-y-2 md:hidden">
              {data.items.map((j: any) => (
                <li key={j.id} className={`rounded-xl border bg-card p-3 ${j.status === "expired" ? "opacity-60" : ""}`}>
                  <Link href={`/jobs/${j.id}`} className="font-medium hover:text-primary"><bdi>{j.title}</bdi></Link>
                  <div className="text-xs text-muted-foreground">
                    <bdi>{j.company_name || "شرکت نامشخص"}</bdi> · {SOURCE_NAME[j.source]} · {[j.city, j.work_mode && WORK_MODE[j.work_mode]].filter(Boolean).join(" · ")}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">{j.categories.map((c: any) => <CategoryBadge key={c.category} category={c.category} sub={c.subcategory} />)}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <SalaryBadge status={j.salary_status} />
                    {j.salary_status !== "unknown" && <span className="num">{salaryRange(j.salary_min, j.salary_max)}</span>}
                    <QualityBadge score={j.quality_score} />
                    <bdi className="ltr text-muted-foreground">{SENIORITY[j.seniority]}</bdi>
                    {j.match_score !== undefined && <span className="num">تطابق {n(j.match_score)}٪</span>}
                  </div>
                </li>
              ))}
            </ul>
            <Card className="hidden md:block">
              <Table>
                <THead>
                  <TR>
                    <TH>عنوان / شرکت</TH><TH>دسته</TH><TH>محل / شیوه</TH><TH>سطح</TH><TH>حقوق</TH><TH>کیفیت</TH>
                    {data.items[0]?.match_score !== undefined && <TH>تطابق</TH>}<TH>زمان</TH><TH />
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((j: any) => (
                    <TR key={j.id} className={j.status === "expired" ? "opacity-60" : ""}>
                      <TD className="min-w-56">
                        <Link href={`/jobs/${j.id}`} className="font-medium hover:text-primary hover:underline"><bdi>{j.title}</bdi></Link>
                        <div className="text-xs text-muted-foreground">
                          <bdi>{j.company_name || "شرکت نامشخص"}</bdi> · {SOURCE_NAME[j.source]}
                          {j.status === "expired" && <Badge variant="secondary" className="ms-1">منقضی</Badge>}
                        </div>
                      </TD>
                      <TD><div className="flex max-w-56 flex-wrap gap-1">{j.categories.map((c: any) => <CategoryBadge key={c.category} category={c.category} sub={c.subcategory} />)}</div></TD>
                      <TD className="whitespace-nowrap text-xs">
                        {[j.province, j.city].filter(Boolean).join(" / ") || "—"}
                        <div className="text-muted-foreground">{j.work_mode ? WORK_MODE[j.work_mode] : "نامشخص"}</div>
                      </TD>
                      <TD className="text-xs"><bdi className="ltr">{SENIORITY[j.seniority]}</bdi></TD>
                      <TD className="whitespace-nowrap text-xs">
                        <SalaryBadge status={j.salary_status} />
                        {j.salary_status !== "unknown" && <div className="num mt-1">{salaryRange(j.salary_min, j.salary_max)}</div>}
                      </TD>
                      <TD><QualityBadge score={j.quality_score} /></TD>
                      {j.match_score !== undefined && <TD className="num">{n(j.match_score)}٪</TD>}
                      <TD className="whitespace-nowrap text-xs text-muted-foreground" title={j.published_at ? "تاریخ انتشار در منبع" : "اولین مشاهده توسط سامانه"}>
                        {j.published_at ? `انتشار ${ago(j.published_at)}` : `مشاهده ${ago(j.first_seen_at)}`}
                      </TD>
                      <TD>
                        <a href={j.canonical_url} target="_blank" rel="noopener noreferrer nofollow" aria-label="آگهی اصلی" className="text-muted-foreground hover:text-primary">
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>
            </>
          )}
          {data && data.total > pageSize && (
            <div className="flex items-center justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronRight />قبلی</Button>
              <span className="num text-sm">صفحه {n(page)} از {n(pages)}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>بعدی<ChevronLeft /></Button>
            </div>
          )}
        </div>
      </div>
      <SaveSearchDialog open={saveOpen} onOpenChange={setSaveOpen} filters={filters} />
    </div>
  );
}

function SaveSearchDialog({ open, onOpenChange, filters }: { open: boolean; onOpenChange: (o: boolean) => void; filters: Filters }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api("/saved-searches", { method: "POST", json: { name, filters: filtersToApi(filters) } });
      toast.ok("فیلتر ذخیره شد. برای فعال‌سازی هشدار به صفحه «جست‌وجوها و هشدارها» بروید.");
      onOpenChange(false);
      setName("");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>ذخیره فیلتر</DialogTitle>
        <DialogDescription>فیلترهای فعلی با این نام ذخیره می‌شوند و می‌توانید برایشان هشدار ایمیل/تلگرام تعریف کنید.</DialogDescription>
        <div className="space-y-1.5">
          <Label htmlFor="ss-name">نام</Label>
          <Input id="ss-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="مثلاً DevOps تهران ارشد" />
        </div>
        <Button onClick={save} disabled={!name.trim() || busy}>{busy && <Spinner />}ذخیره</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <JobsExplorer />
    </Suspense>
  );
}

