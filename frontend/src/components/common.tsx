"use client";
import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, OctagonX } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CATEGORY_COLOR, CATEGORY_LABEL, SALARY_STATUS, SOURCE_STATUS } from "@/lib/labels";
import { errorText } from "@/lib/api";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-bold sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="pt-4 sm:pt-5">
        <div className="text-sm text-muted-foreground">{label}</div>
        <div className="num mt-1 text-2xl font-bold">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

export function CategoryBadge({ category, sub }: { category: string; sub?: string | null }) {
  return (
    <Badge variant="outline" className="gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ background: CATEGORY_COLOR[category] }} aria-hidden />
      <bdi className="ltr">{sub || CATEGORY_LABEL[category] || category}</bdi>
    </Badge>
  );
}

const STATUS_ICON = { good: CheckCircle2, warning: AlertTriangle, critical: OctagonX, secondary: CircleSlash } as const;

export function SourceStatus({ status, running }: { status: string; running?: boolean }) {
  if (running)
    return (
      <Badge variant="default">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        در حال جمع‌آوری
      </Badge>
    );
  const s = SOURCE_STATUS[status] || SOURCE_STATUS.unknown;
  const Icon = STATUS_ICON[s.tone];
  return (
    <Badge variant={s.tone}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {s.label}
    </Badge>
  );
}

export function SalaryBadge({ status }: { status: string }) {
  const v = status === "reported" ? "good" : status === "estimated" ? "default" : "secondary";
  return <Badge variant={v as any}>{SALARY_STATUS[status] || status}</Badge>;
}

export function QualityBadge({ score }: { score?: number | null }) {
  if (score === null || score === undefined) return <span className="text-muted-foreground">—</span>;
  const v = score >= 70 ? "good" : score >= 45 ? "warning" : "critical";
  return (
    <Badge variant={v as any} className="num" title="کیفیت و شفافیت اطلاعات آگهی، نه اعتبار شرکت">
      {new Intl.NumberFormat("fa-IR").format(score)}/۱۰۰
    </Badge>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-[var(--status-critical)]/40 p-3 text-sm" role="alert" data-error-box>
      <OctagonX className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-critical)]" />
      <span className="prose-auto">خطا: {errorText(error)}</span>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">{children}</div>;
}

export function Spinner() {
  return <Loader2 className="h-4 w-4 animate-spin" />;
}
