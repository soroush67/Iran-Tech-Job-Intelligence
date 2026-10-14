"use client";
import { useState } from "react";
import useSWR from "swr";
import { qs } from "@/lib/api";
import { n, pct, toman } from "@/lib/format";
import { CATEGORIES, CATEGORY_COLOR, CATEGORY_LABEL, SENIORITY, WORK_MODE } from "@/lib/labels";
import { HBars, TrendLines } from "@/components/charts";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/common";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const weekFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { month: "short", day: "numeric" });

export default function InsightsPage() {
  const [weeks, setWeeks] = useState("12");
  const [cat, setCat] = useState<string>("devops");
  const { data, error } = useSWR(`/insights${qs({ weeks })}`);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={4} />;
  if (data.total_active === 0) return (
    <div><PageHeader title="تحلیل بازار" /><Empty>هنوز داده کافی برای تحلیل جمع‌آوری نشده است.</Empty></div>
  );

  // trend rows: one per week, a column per category (missing -> 0)
  const byWeek: Record<string, any> = {};
  for (const r of data.trend) {
    const k = r.week;
    byWeek[k] ||= { label: weekFmt.format(new Date(k)) };
    byWeek[k][r.category] = r.count;
  }
  const trend = Object.keys(byWeek).sort().map((k) => byWeek[k]);
  const series = CATEGORIES.map((c) => ({ key: c, name: CATEGORY_LABEL[c], color: CATEGORY_COLOR[c] }));
  const demandByCat = CATEGORIES.map((c) => ({
    c, total: data.demand.filter((d: any) => d.category === c).reduce((s: number, d: any) => s + d.count, 0),
  }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="تحلیل بازار"
        description={data.coverage_note}
        actions={
          <div className="w-40">
            <Select value={weeks} onValueChange={setWeeks}>
              <SelectTrigger aria-label="بازه زمانی"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="4">۴ هفته اخیر</SelectItem>
                <SelectItem value="12">۱۲ هفته اخیر</SelectItem>
                <SelectItem value="26">۲۶ هفته اخیر</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {demandByCat.map(({ c, total }) => (
          <Card key={c}>
            <CardContent className="pt-4">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="h-2 w-2 rounded-full" style={{ background: CATEGORY_COLOR[c] }} aria-hidden /><bdi className="ltr">{CATEGORY_LABEL[c]}</bdi>
              </div>
              <div className="num mt-1 text-2xl font-bold">{n(total)}</div>
              <div className="text-xs text-muted-foreground">آگهی فعال</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle>تغییر تقاضا در طول زمان</CardTitle><CardDescription>آگهی‌های جدید در هر هفته (بر اساس اولین مشاهده)</CardDescription></CardHeader>
        <CardContent>{trend.length < 2 ? <Empty>برای روند حداقل دو هفته داده لازم است.</Empty> : <TrendLines data={trend} series={series} />}</CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>فناوری‌های پرتکرار</CardTitle><CardDescription>در همه آگهی‌های فعال</CardDescription></CardHeader>
          <CardContent><HBars data={data.top_skills.slice(0, 15).map((s: any) => ({ name: s.skill, value: s.count }))} /></CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>مهارت‌های پرتقاضا در هر دسته</CardTitle>
            <div className="w-56 pt-1">
              <Select value={cat} onValueChange={setCat}>
                <SelectTrigger aria-label="دسته"><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{CATEGORY_LABEL[c]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            {(data.skills_by_category[cat] || []).length === 0 ? <Empty>داده‌ای نیست.</Empty> :
              <HBars color={CATEGORY_COLOR[cat]} data={data.skills_by_category[cat].map((s: any) => ({ name: s.skill, value: s.count }))} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>زیرگروه‌های پرتقاضا</CardTitle></CardHeader>
          <CardContent><HBars data={data.demand.slice(0, 12).map((d: any) => ({ name: d.subcategory || CATEGORY_LABEL[d.category], value: d.count }))} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>شهرها، شیوه همکاری و سطح</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <HBars label="شهرها" data={data.cities.map((c: any) => ({ name: c.city, value: c.count }))} />
            <HBars label="شیوه همکاری" data={data.work_modes.map((w: any) => ({ name: WORK_MODE[w.work_mode] || w.work_mode, value: w.count }))} />
            <HBars label="سطح ارشدیت" data={data.seniority.map((s: any) => ({ name: SENIORITY[s.seniority] || s.seniority, value: s.count }))} />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>توزیع حقوق اعلام‌شده</CardTitle>
          <CardDescription>
            {data.salary.note} سهم آگهی‌های فعال با حقوق اعلام‌شده: {pct(data.salary.reported_share)} · حداقل نمونه: {n(data.salary.min_samples)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {data.salary.groups.length === 0 ? <Empty>هنوز آگهی با حقوق اعلام‌شده ثبت نشده است.</Empty> : (
            <Table>
              <THead><TR><TH>دسته</TH><TH>سطح</TH><TH>نمونه</TH><TH>چارک اول</TH><TH>میانه</TH><TH>چارک سوم</TH></TR></THead>
              <TBody>
                {data.salary.groups.map((g: any) => (
                  <TR key={`${g.category}-${g.seniority}`}>
                    <TD><bdi className="ltr">{CATEGORY_LABEL[g.category]}</bdi></TD>
                    <TD><bdi className="ltr">{SENIORITY[g.seniority]}</bdi></TD>
                    <TD className="num">{n(g.samples)}</TD>
                    {g.insufficient ? <TD colSpan={3} className="text-xs text-muted-foreground">نمونه ناکافی — نمایش داده نمی‌شود</TD> : (
                      <><TD className="num">{toman(g.p25)}</TD><TD className="num font-medium">{toman(g.median)}</TD><TD className="num">{toman(g.p75)}</TD></>
                    )}
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
