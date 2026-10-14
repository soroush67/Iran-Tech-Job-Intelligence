"use client";
/* Charts follow the dataviz method: fixed category->color slots (never by rank),
   one axis, thin marks with 4px rounded data-ends, recessive grid, hover tooltip on
   every chart, a legend for >= 2 series, and a table view for every chart. */
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Table2, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { n } from "@/lib/format";

const AXIS = { fontSize: 12, fill: "var(--axis-text)" };

function TooltipBox({ active, payload, label, unit }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md" dir="rtl">
      {label !== undefined && <div className="mb-1 font-medium"><bdi>{label}</bdi></div>}
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.fill }} aria-hidden />
          <span className="text-muted-foreground"><bdi>{p.name}</bdi>:</span>
          <span className="num font-medium">{n(p.value)}{unit || ""}</span>
        </div>
      ))}
    </div>
  );
}

export function ChartFrame({ title, children, table }: { title?: string; children: React.ReactNode; table: React.ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        {title ? <div className="text-sm font-medium">{title}</div> : <span />}
        <Button variant="ghost" size="sm" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>
          {asTable ? <BarChart3 /> : <Table2 />}
          {asTable ? "نمودار" : "جدول"}
        </Button>
      </div>
      {asTable ? table : children}
    </div>
  );
}

/** Single-series horizontal bars (magnitude by item). */
export function HBars({ data, label, valueLabel = "تعداد", color = "var(--series-1)", height }: {
  data: { name: string; value: number }[]; label?: string; valueLabel?: string; color?: string; height?: number;
}) {
  const h = height || Math.max(160, data.length * 28 + 30);
  return (
    <ChartFrame
      title={label}
      table={
        <Table>
          <THead><TR><TH>مورد</TH><TH>{valueLabel}</TH></TR></THead>
          <TBody>{data.map((d) => <TR key={d.name}><TD><bdi>{d.name}</bdi></TD><TD className="num">{n(d.value)}</TD></TR>)}</TBody>
        </Table>
      }
    >
      <div dir="ltr" style={{ height: h }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }} barCategoryGap={6}>
            <CartesianGrid horizontal={false} stroke="var(--grid)" />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} width={130} axisLine={false} tickLine={false} />
            <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--muted)" }} />
            <Bar dataKey="value" name={valueLabel} fill={color} radius={[0, 4, 4, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/** Multi-series lines over time; series = categories with fixed colors. */
export function TrendLines({ data, series, label }: {
  data: Record<string, any>[]; series: { key: string; name: string; color: string }[]; label?: string;
}) {
  return (
    <ChartFrame
      title={label}
      table={
        <Table>
          <THead><TR><TH>هفته</TH>{series.map((s) => <TH key={s.key}><bdi>{s.name}</bdi></TH>)}</TR></THead>
          <TBody>
            {data.map((d) => (
              <TR key={d.label}><TD>{d.label}</TD>{series.map((s) => <TD key={s.key} className="num">{n(d[s.key] || 0)}</TD>)}</TR>
            ))}
          </TBody>
        </Table>
      }
    >
      <div dir="ltr" className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} width={36} />
            <Tooltip content={<TooltipBox />} cursor={{ stroke: "var(--axis-text)", strokeDasharray: "3 3" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2}
                dot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} activeDot={{ r: 5 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/** Per-category bars (identity encoded by the fixed category color + axis label). */
export function CategoryBars({ data, label }: { data: { name: string; value: number; color: string }[]; label?: string }) {
  return (
    <ChartFrame
      title={label}
      table={
        <Table>
          <THead><TR><TH>دسته</TH><TH>تعداد</TH></TR></THead>
          <TBody>{data.map((d) => <TR key={d.name}><TD><bdi>{d.name}</bdi></TD><TD className="num">{n(d.value)}</TD></TR>)}</TBody>
        </Table>
      }
    >
      <div dir="ltr" style={{ height: Math.max(160, data.length * 34 + 30) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }} barCategoryGap={8}>
            <CartesianGrid horizontal={false} stroke="var(--grid)" />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} width={150} axisLine={false} tickLine={false} />
            <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--muted)" }} />
            <Bar dataKey="value" name="تعداد آگهی فعال" radius={[0, 4, 4, 0]} maxBarSize={20}
              shape={(p: any) => <rect x={p.x} y={p.y} width={Math.max(p.width, 0)} height={p.height} rx={4} fill={p.payload.color} />} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
