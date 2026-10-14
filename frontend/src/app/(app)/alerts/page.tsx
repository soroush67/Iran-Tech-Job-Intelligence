"use client";
import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { BellPlus, Mail, Search, Send, Trash2 } from "lucide-react";
import { api, errorText, qs } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { CATEGORY_LABEL, EVENT } from "@/lib/labels";
import { useMe } from "@/components/app-shell";
import { Empty, ErrorBox, Loading, PageHeader, Spinner } from "@/components/common";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const DELIVERY: Record<string, string> = { sent: "ارسال شد", pending: "در انتظار/تلاش مجدد", failed: "ناموفق", skipped: "رد شد (سقف ساعتی)" };

type Sub = {
  id?: number; saved_search_id: number | null; channel: "email" | "telegram"; event_types: string[];
  frequency: "instant" | "daily"; categories: string[]; min_match_score: number | null; active: boolean;
};

function describeFilters(f: any): string {
  const parts: string[] = [];
  if (f.q) parts.push(`«${f.q}»`);
  if (f.categories?.length) parts.push(f.categories.map((c: string) => CATEGORY_LABEL[c] || c).join("، "));
  if (f.cities?.length) parts.push(f.cities.join("، "));
  if (f.provinces?.length) parts.push(f.provinces.join("، "));
  if (f.work_modes?.length) parts.push(f.work_modes.join("، "));
  if (f.seniority?.length) parts.push(f.seniority.join("، "));
  if (f.skills?.length) parts.push(f.skills.join(", "));
  return parts.join(" · ") || "همه آگهی‌های مرتبط";
}

function SubscriptionDialog({ open, onOpenChange, initial, onSaved }: {
  open: boolean; onOpenChange: (o: boolean) => void; initial: Sub; onSaved: () => void;
}) {
  const [s, setS] = useState<Sub>(initial);
  const [busy, setBusy] = useState(false);
  const toggle = (k: "event_types" | "categories", v: string) =>
    setS({ ...s, [k]: s[k].includes(v) ? s[k].filter((x) => x !== v) : [...s[k], v] });
  async function save() {
    setBusy(true);
    try {
      if (s.id) await api(`/subscriptions/${s.id}`, { method: "PUT", json: s });
      else await api("/subscriptions", { method: "POST", json: s });
      toast.ok("هشدار ذخیره شد");
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{s.id ? "ویرایش هشدار" : "هشدار جدید"}</DialogTitle>
        <DialogDescription>چه رویدادهایی، از چه کانالی و با چه تناوبی ارسال شود.</DialogDescription>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>کانال</Label>
            <Select value={s.channel} onValueChange={(v) => setS({ ...s, channel: v as any })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="email">ایمیل</SelectItem><SelectItem value="telegram">تلگرام</SelectItem></SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>تناوب</Label>
            <Select value={s.frequency} onValueChange={(v) => setS({ ...s, frequency: v as any })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="instant">فوری</SelectItem><SelectItem value="daily">گزارش روزانه</SelectItem></SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-2">
          <Label>رویدادها</Label>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(EVENT).map(([k, v]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <Checkbox checked={s.event_types.includes(k)} onCheckedChange={() => toggle("event_types", k)} />{v}
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label>فقط این دسته‌ها (خالی = همه)</Label>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <Checkbox checked={s.categories.includes(k)} onCheckedChange={() => toggle("categories", k)} /><bdi className="ltr">{v}</bdi>
              </label>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="mm">حداقل امتیاز تطابق با پروفایل (خالی = بدون شرط)</Label>
          <Input id="mm" type="number" min={0} max={100} value={s.min_match_score ?? ""}
            onChange={(e) => setS({ ...s, min_match_score: e.target.value === "" ? null : Number(e.target.value) })} />
        </div>
        <label className="flex items-center gap-2 text-sm"><Switch checked={s.active} onCheckedChange={(v) => setS({ ...s, active: v })} />فعال</label>
        <Button onClick={save} disabled={busy || s.event_types.length === 0}>{busy && <Spinner />}ذخیره</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function AlertsPage() {
  const { data, error, mutate } = useSWR("/saved-searches");
  const { data: deliveries } = useSWR("/notifications/deliveries", { refreshInterval: 60_000 });
  const { data: me } = useMe();
  const [dialog, setDialog] = useState<Sub | null>(null);

  const newSub = (saved_search_id: number | null): Sub => ({
    saved_search_id, channel: "email", event_types: ["NEW_JOB"], frequency: "instant", categories: [], min_match_score: null, active: true,
  });

  async function del(path: string) {
    if (!confirm("حذف شود؟")) return;
    try {
      await api(path, { method: "DELETE" });
      mutate();
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  async function toggleActive(sub: Sub) {
    try {
      await api(`/subscriptions/${sub.id}`, { method: "PUT", json: { ...sub, active: !sub.active } });
      mutate();
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  const SubList = ({ subs }: { subs: Sub[] }) => (
    <div className="space-y-2">
      {subs.map((x) => (
        <div key={x.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2 text-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            {x.channel === "email" ? <Mail className="h-4 w-4" aria-label="ایمیل" /> : <Send className="h-4 w-4" aria-label="تلگرام" />}
            <Badge variant="secondary">{x.frequency === "instant" ? "فوری" : "روزانه"}</Badge>
            {x.event_types.map((e) => <Badge key={e} variant="outline">{EVENT[e]}</Badge>)}
            {x.min_match_score !== null && <Badge variant="outline">تطابق ≥ {x.min_match_score}</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={x.active} onCheckedChange={() => toggleActive(x)} aria-label="فعال/غیرفعال" />
            <Button variant="ghost" size="sm" onClick={() => setDialog(x)}>ویرایش</Button>
            <Button variant="ghost" size="icon" onClick={() => del(`/subscriptions/${x.id}`)} aria-label="حذف هشدار"><Trash2 /></Button>
          </div>
        </div>
      ))}
    </div>
  );

  const channelWarnings = me && (
    <div className="space-y-1 text-xs text-muted-foreground">
      {!me.notify_email_verified && <p>• برای هشدار ایمیلی، ابتدا در <Link className="text-primary underline" href="/settings">تنظیمات</Link> ایمیل خود را ثبت و تأیید کنید.</p>}
      {!me.telegram && <p>• برای هشدار تلگرامی، ابتدا در <Link className="text-primary underline" href="/settings">تنظیمات</Link> تلگرام را متصل کنید.</p>}
    </div>
  );

  return (
    <div className="space-y-4">
      <PageHeader title="جست‌وجوها و هشدارها" description="اعلان‌ها فقط بر اساس فیلترهای ذخیره‌شده خودتان ارسال می‌شوند"
        actions={<Button variant="outline" onClick={() => setDialog(newSub(null))}><BellPlus />هشدار برای همه آگهی‌ها</Button>} />
      {channelWarnings}
      {error ? <ErrorBox error={error} /> : !data ? <Loading /> : (
        <>
          {data.items.length === 0 && (
            <Empty>جست‌وجوی ذخیره‌شده‌ای ندارید. در <Link className="text-primary underline" href="/jobs">صفحه آگهی‌ها</Link> فیلتر بزنید و «ذخیره فیلتر» را انتخاب کنید.</Empty>
          )}
          {data.items.map((s: any) => (
            <Card key={s.id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <CardTitle>{s.name}</CardTitle>
                    <CardDescription className="prose-auto">{describeFilters(s.filters)}</CardDescription>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="outline" size="sm" asChild><Link href={`/jobs${qs(s.filters)}`}><Search />نمایش نتایج</Link></Button>
                    <Button variant="outline" size="sm" onClick={() => setDialog(newSub(s.id))}><BellPlus />هشدار</Button>
                    <Button variant="ghost" size="icon" onClick={() => del(`/saved-searches/${s.id}`)} aria-label="حذف جست‌وجو"><Trash2 /></Button>
                  </div>
                </div>
              </CardHeader>
              {s.subscriptions.length > 0 && <CardContent><SubList subs={s.subscriptions} /></CardContent>}
            </Card>
          ))}
          {data.unattached_subscriptions.length > 0 && (
            <Card>
              <CardHeader><CardTitle>هشدارهای همه آگهی‌های مرتبط</CardTitle></CardHeader>
              <CardContent><SubList subs={data.unattached_subscriptions} /></CardContent>
            </Card>
          )}
        </>
      )}
      <Card>
        <CardHeader><CardTitle>آخرین اعلان‌های ارسالی</CardTitle></CardHeader>
        <CardContent>
          {!deliveries?.items?.length ? <Empty>هنوز اعلانی ارسال نشده.</Empty> : (
            <Table>
              <THead><TR><TH>زمان</TH><TH>کانال</TH><TH>موضوع</TH><TH>وضعیت</TH></TR></THead>
              <TBody>
                {deliveries.items.map((d: any) => (
                  <TR key={d.id}>
                    <TD className="text-xs">{dateTime(d.created_at)}</TD>
                    <TD>{d.channel === "email" ? "ایمیل" : "تلگرام"}</TD>
                    <TD className="text-xs"><bdi>{d.digest_key ? "گزارش روزانه" : d.title}</bdi></TD>
                    <TD><Badge variant={d.status === "sent" ? "good" : d.status === "failed" ? "critical" : "warning"}>{DELIVERY[d.status]}</Badge>
                      {d.last_error && <div className="text-xs text-muted-foreground prose-auto">{d.last_error}</div>}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
      {dialog && <SubscriptionDialog key={dialog.id ?? `new-${dialog.saved_search_id}`} open onOpenChange={(o) => !o && setDialog(null)} initial={dialog} onSaved={() => mutate()} />}
    </div>
  );
}
