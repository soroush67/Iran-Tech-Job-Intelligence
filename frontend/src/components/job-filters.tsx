"use client";
import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { CATEGORY_LABEL, JOB_STATUS, SALARY_STATUS, SENIORITY, SOURCE_NAME, WORK_MODE } from "@/lib/labels";

export type Filters = {
  q?: string; title?: string; company?: string;
  sources: string[]; categories: string[]; subcategories: string[]; provinces: string[]; cities: string[];
  work_modes: string[]; seniority: string[]; skills: string[]; salary_status: string[]; status: string[];
  salary_min?: number; salary_max?: number; quality_min?: number;
  published_from?: string; published_to?: string; changed_from?: string;
};

export const LIST_KEYS = ["sources", "categories", "subcategories", "provinces", "cities", "work_modes", "seniority",
  "skills", "salary_status", "status"] as const;
export const SCALAR_KEYS = ["q", "title", "company", "salary_min", "salary_max", "quality_min", "published_from",
  "published_to", "changed_from"] as const;

export const EMPTY: Filters = {
  sources: [], categories: [], subcategories: [], provinces: [], cities: [], work_modes: [], seniority: [],
  skills: [], salary_status: [], status: ["active"],
};

export function filtersFromSearch(sp: URLSearchParams): Filters {
  const f: any = { ...EMPTY };
  for (const k of LIST_KEYS) {
    const v = sp.getAll(k);
    if (v.length) f[k] = v;
  }
  for (const k of SCALAR_KEYS) {
    const v = sp.get(k);
    if (v) f[k] = ["salary_min", "salary_max", "quality_min"].includes(k) ? Number(v) : v;
  }
  return f;
}

export function filtersToParams(f: Filters): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of LIST_KEYS) if (f[k]?.length) out[k] = f[k];
  for (const k of SCALAR_KEYS) if (f[k] !== undefined && f[k] !== "") out[k] = f[k];
  return out;
}

/** Saved-search payload for the API (JobFilters schema). */
export function filtersToApi(f: Filters) {
  const p: any = filtersToParams(f);
  for (const k of ["published_from", "published_to", "changed_from"]) if (p[k]) p[k] = new Date(p[k]).toISOString();
  return p;
}

function Chips({ options, value, onChange, ltr }: {
  options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void; ltr?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button key={o.value} type="button" aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== o.value) : [...value, o.value])}
            className={cn("rounded-md border px-2 py-1 text-xs transition-colors",
              on ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted")}>
            {ltr ? <bdi className="ltr">{o.label}</bdi> : o.label}
          </button>
        );
      })}
    </div>
  );
}

function PickList({ label, options, value, onChange, placeholder }: {
  label: string; options: { value: string; count?: number }[]; value: string[]; onChange: (v: string[]) => void; placeholder: string;
}) {
  const rest = options.filter((o) => !value.includes(o.value));
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Select value="" onValueChange={(v) => v && onChange([...value, v])}>
        <SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger>
        <SelectContent>
          {rest.length === 0 ? <div className="p-2 text-xs text-muted-foreground">موردی نیست</div> :
            rest.map((o) => <SelectItem key={o.value} value={o.value}>{o.value}{o.count ? ` (${o.count})` : ""}</SelectItem>)}
        </SelectContent>
      </Select>
      <Selected value={value} onChange={onChange} />
    </div>
  );
}

function Selected({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  if (!value.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {value.map((v) => (
        <span key={v} className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-xs">
          <bdi>{v}</bdi>
          <button type="button" aria-label={`حذف ${v}`} onClick={() => onChange(value.filter((x) => x !== v))}><X className="h-3 w-3" /></button>
        </span>
      ))}
    </div>
  );
}

function SkillPicker({ value, onChange, suggestions }: { value: string[]; onChange: (v: string[]) => void; suggestions: string[] }) {
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setText("");
  };
  return (
    <div className="space-y-1.5">
      <Label htmlFor="skill-input">مهارت‌های ضروری (همه)</Label>
      <div className="flex gap-1">
        <Input id="skill-input" dir="ltr" list="skill-suggestions" value={text} placeholder="Kubernetes"
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())} />
        <Button type="button" variant="outline" size="icon" onClick={add} aria-label="افزودن مهارت"><Plus /></Button>
      </div>
      <datalist id="skill-suggestions">{suggestions.map((s) => <option key={s} value={s} />)}</datalist>
      <Selected value={value} onChange={onChange} />
    </div>
  );
}

export function FilterPanel({ f, set, facets }: { f: Filters; set: (f: Filters) => void; facets: any }) {
  const upd = (patch: Partial<Filters>) => set({ ...f, ...patch });
  const num = (v: string) => (v === "" ? undefined : Number(v));
  const subcats = (facets?.subcategories || []).filter((s: any) => !f.categories.length || f.categories.includes(s.category));
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="q">جست‌وجو</Label>
        <Input id="q" value={f.q || ""} placeholder="عنوان، شرکت، مهارت، متن آگهی" onChange={(e) => upd({ q: e.target.value || undefined })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="title">عنوان</Label>
          <Input id="title" value={f.title || ""} onChange={(e) => upd({ title: e.target.value || undefined })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="company">شرکت</Label>
          <Input id="company" value={f.company || ""} onChange={(e) => upd({ company: e.target.value || undefined })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>دسته شغلی</Label>
        <Chips ltr options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} value={f.categories}
          onChange={(categories) => upd({ categories })} />
      </div>
      {subcats.length > 0 && (
        <div className="space-y-1.5">
          <Label>زیرگروه</Label>
          <Chips ltr options={subcats.slice(0, 24).map((s: any) => ({ value: s.subcategory, label: `${s.subcategory} (${s.count})` }))}
            value={f.subcategories} onChange={(subcategories) => upd({ subcategories })} />
        </div>
      )}
      <div className="space-y-1.5">
        <Label>منبع</Label>
        <Chips options={(facets?.sources || []).map((s: any) => ({ value: s.key, label: SOURCE_NAME[s.key] || s.name }))}
          value={f.sources} onChange={(sources) => upd({ sources })} />
      </div>
      <PickList label="استان" placeholder="انتخاب استان" options={facets?.provinces || []} value={f.provinces} onChange={(provinces) => upd({ provinces })} />
      <PickList label="شهر" placeholder="انتخاب شهر" options={facets?.cities || []} value={f.cities} onChange={(cities) => upd({ cities })} />
      <div className="space-y-1.5">
        <Label>شیوه همکاری</Label>
        <Chips options={["onsite", "hybrid", "remote"].map((v) => ({ value: v, label: WORK_MODE[v] }))} value={f.work_modes}
          onChange={(work_modes) => upd({ work_modes })} />
      </div>
      <div className="space-y-1.5">
        <Label>سطح ارشدیت</Label>
        <Chips ltr options={Object.entries(SENIORITY).map(([value, label]) => ({ value, label }))} value={f.seniority}
          onChange={(seniority) => upd({ seniority })} />
      </div>
      <SkillPicker value={f.skills} onChange={(skills) => upd({ skills })} suggestions={(facets?.skills || []).map((s: any) => s.value)} />
      <div className="space-y-1.5">
        <Label>محدوده حقوق ماهانه (میلیون تومان)</Label>
        <div className="grid grid-cols-2 gap-2">
          <Input type="number" min={0} placeholder="از" aria-label="حداقل حقوق"
            value={f.salary_min ? f.salary_min / 1_000_000 : ""} onChange={(e) => upd({ salary_min: e.target.value ? Number(e.target.value) * 1_000_000 : undefined })} />
          <Input type="number" min={0} placeholder="تا" aria-label="حداکثر حقوق"
            value={f.salary_max ? f.salary_max / 1_000_000 : ""} onChange={(e) => upd({ salary_max: e.target.value ? Number(e.target.value) * 1_000_000 : undefined })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>نوع حقوق</Label>
        <Chips options={Object.entries(SALARY_STATUS).map(([value, label]) => ({ value, label }))} value={f.salary_status}
          onChange={(salary_status) => upd({ salary_status })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="quality">حداقل کیفیت آگهی (۰ تا ۱۰۰)</Label>
        <Input id="quality" type="number" min={0} max={100} value={f.quality_min ?? ""} onChange={(e) => upd({ quality_min: num(e.target.value) })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="pf">انتشار از</Label>
          <Input id="pf" type="date" dir="ltr" value={f.published_from || ""} onChange={(e) => upd({ published_from: e.target.value || undefined })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pt">انتشار تا</Label>
          <Input id="pt" type="date" dir="ltr" value={f.published_to || ""} onChange={(e) => upd({ published_to: e.target.value || undefined })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="cf">آخرین تغییر از</Label>
        <Input id="cf" type="date" dir="ltr" value={f.changed_from || ""} onChange={(e) => upd({ changed_from: e.target.value || undefined })} />
      </div>
      <div className="space-y-1.5">
        <Label>وضعیت</Label>
        <Chips options={["active", "expired"].map((v) => ({ value: v, label: JOB_STATUS[v] }))} value={f.status} onChange={(status) => upd({ status })} />
      </div>
      <Button variant="outline" className="w-full" onClick={() => set({ ...EMPTY })}>پاک کردن فیلترها</Button>
      <p className="text-xs text-muted-foreground">تاریخ انتشار اگر در منبع نباشد، «اولین مشاهده» ملاک فیلتر است.</p>
    </div>
  );
}
