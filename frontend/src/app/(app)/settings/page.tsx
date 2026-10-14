"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Bot, Database, KeyRound, Mail, PlugZap, RefreshCw, Send, ShieldCheck, Upload, User, Users } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { dateTime, n } from "@/lib/format";
import { useMe } from "@/components/app-shell";
import { ErrorBox, Loading, PageHeader, Spinner } from "@/components/common";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WORK_MODE } from "@/lib/labels";

function useAction() {
  const [busy, setBusy] = useState(false);
  async function run<T>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) toast.ok(ok);
      return r;
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

const split = (s: string) => s.split(/[,،\n]/).map((x) => x.trim()).filter(Boolean);

function ProfileTab() {
  const { data: me, mutate } = useMe();
  const [f, setF] = useState<any>(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const { busy, run } = useAction();
  useEffect(() => {
    if (me && !f) {
      const p = me.profile || {};
      setF({
        display_name: me.display_name || "", skills: (p.skills || []).join(", "), preferred_skills: (p.preferred_skills || []).join(", "),
        years_experience: p.years_experience ?? "", cities: (p.cities || []).join("، "), work_modes: p.work_modes || [],
      });
    }
  }, [me, f]);
  if (!f) return <Loading />;
  const save = () => run(async () => {
    await api("/auth/me/profile", { method: "PUT", json: {
      display_name: f.display_name || null, skills: split(f.skills), preferred_skills: split(f.preferred_skills),
      years_experience: f.years_experience === "" ? null : Number(f.years_experience), cities: split(f.cities), work_modes: f.work_modes,
    } });
    mutate();
  }, "پروفایل ذخیره شد");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>پروفایل مهارت (برای امتیاز تطابق)</CardTitle>
          <CardDescription>امتیاز تطابق از مهارت‌های ضروری، ترجیحی، سابقه، شهر و شیوه همکاری جداگانه محاسبه می‌شود.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="dn">نام نمایشی</Label><Input id="dn" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label htmlFor="sk">مهارت‌های من (با کاما)</Label>
            <Textarea id="sk" dir="ltr" placeholder="Linux, Docker, Kubernetes, Terraform" value={f.skills} onChange={(e) => setF({ ...f, skills: e.target.value })} /></div>
          <div className="space-y-1.5"><Label htmlFor="pk">فناوری‌های ترجیحی</Label>
            <Input id="pk" dir="ltr" placeholder="ArgoCD, Go" value={f.preferred_skills} onChange={(e) => setF({ ...f, preferred_skills: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label htmlFor="ye">سال سابقه</Label>
              <Input id="ye" type="number" min={0} max={60} value={f.years_experience} onChange={(e) => setF({ ...f, years_experience: e.target.value })} /></div>
            <div className="space-y-1.5"><Label htmlFor="ct">شهرها</Label>
              <Input id="ct" placeholder="تهران، کرج" value={f.cities} onChange={(e) => setF({ ...f, cities: e.target.value })} /></div>
          </div>
          <div className="space-y-1.5"><Label>شیوه همکاری قابل قبول</Label>
            <div className="flex gap-4">
              {["onsite", "hybrid", "remote"].map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={f.work_modes.includes(m)} onCheckedChange={(v) =>
                    setF({ ...f, work_modes: v ? [...f.work_modes, m] : f.work_modes.filter((x: string) => x !== m) })} />{WORK_MODE[m]}
                </label>
              ))}
            </div>
          </div>
          <Button onClick={save} disabled={busy}>{busy && <Spinner />}ذخیره</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>تغییر رمز عبور</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="cp">رمز فعلی</Label><Input id="cp" type="password" dir="ltr" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></div>
          <div className="space-y-1.5"><Label htmlFor="np">رمز جدید (حداقل ۸ نویسه)</Label><Input id="np" type="password" dir="ltr" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></div>
          <Button variant="outline" disabled={busy || pw.new_password.length < 8}
            onClick={() => run(() => api("/auth/me/password", { method: "PUT", json: pw }), "رمز تغییر کرد").then(() => setPw({ current_password: "", new_password: "" }))}>
            تغییر رمز</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function EmailTab() {
  const { data: me, mutate } = useMe();
  const [email, setEmail] = useState("");
  const { busy, run } = useAction();
  if (!me) return <Loading />;
  return (
    <Card className="max-w-xl">
      <CardHeader><CardTitle>ایمیل اعلان‌ها</CardTitle>
        <CardDescription>پس از ثبت، لینک تأیید ارسال می‌شود؛ تا تأیید نشود هیچ اعلانی به این نشانی نمی‌رود.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm">
          نشانی فعلی: <bdi className="ltr">{me.notify_email || "—"}</bdi>{" "}
          {me.notify_email && (me.notify_email_verified ? <Badge variant="good">تأییدشده</Badge> : <Badge variant="warning">در انتظار تأیید</Badge>)}
        </div>
        <div className="flex gap-2">
          <Input type="email" dir="ltr" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button disabled={busy || !email} onClick={() => run(() => api("/notifications/email", { method: "POST", json: { email } }), "لینک تأیید ارسال شد").then(() => mutate())}>
            {busy && <Spinner />}ثبت و ارسال لینک</Button>
        </div>
        <Button variant="outline" disabled={busy || !me.notify_email_verified}
          onClick={() => run(() => api("/notifications/test", { method: "POST", json: { channel: "email" } }), "ایمیل آزمایشی ارسال شد")}>
          <Mail />ارسال ایمیل آزمایشی</Button>
        <p className="text-xs text-muted-foreground">لغو هر هشدار: از صفحه <Link className="text-primary underline" href="/alerts">هشدارها</Link> یا لینک «لغو» در پایین هر ایمیل.</p>
      </CardContent>
    </Card>
  );
}

function TelegramTab() {
  const { data: st, mutate } = useSWR("/telegram/status");
  const [link, setLink] = useState<any>(null);
  const { busy, run } = useAction();
  if (!st) return <Loading />;
  return (
    <Card className="max-w-xl">
      <CardHeader><CardTitle>اتصال تلگرام</CardTitle>
        <CardDescription>اتصال با کد یک‌بارمصرف ۱۰ دقیقه‌ای انجام می‌شود؛ شناسه چت فقط از خود تلگرام دریافت می‌شود.</CardDescription></CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!st.bot_configured && <p className="text-[var(--status-critical)]">ربات تلگرام روی سرور تنظیم نشده است (TELEGRAM_BOT_TOKEN و TELEGRAM_BOT_USERNAME در .env).</p>}
        <div>وضعیت: {st.status === "active" ? <Badge variant="good">متصل {st.username ? <bdi className="ltr">@{st.username}</bdi> : null}</Badge> : <Badge variant="secondary">متصل نیست</Badge>}
          {st.connected_at && <span className="ms-2 text-xs text-muted-foreground">{dateTime(st.connected_at)}</span>}</div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || !st.bot_configured} onClick={() => run(() => api("/telegram/connect", { method: "POST" })).then((r) => r && setLink(r))}>
            <PlugZap />{st.status === "active" ? "اتصال به حساب دیگر" : "اتصال تلگرام"}</Button>
          {st.status === "active" && (
            <>
              <Button variant="outline" disabled={busy} onClick={() => run(() => api("/notifications/test", { method: "POST", json: { channel: "telegram" } }), "پیام آزمایشی ارسال شد")}><Send />پیام آزمایشی</Button>
              <Button variant="ghost" disabled={busy} onClick={() => run(() => api("/telegram/connect", { method: "DELETE" }), "اتصال قطع شد").then(() => mutate())}>قطع اتصال</Button>
            </>
          )}
        </div>
        {link && (
          <div className="space-y-2 rounded-md border p-3">
            <p>روی لینک زیر بزنید و در تلگرام «Start» را انتخاب کنید (تا ۱۰ دقیقه معتبر است):</p>
            <a className="break-all text-primary underline ltr" href={link.deep_link} target="_blank" rel="noopener noreferrer">{link.deep_link}</a>
            <p className="text-xs text-muted-foreground">یا این متن را برای ربات بفرستید: <code className="ltr">{link.manual}</code></p>
            <Button size="sm" variant="outline" onClick={() => mutate()}>بررسی وضعیت</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AITab() {
  const { data, error, mutate } = useSWR("/admin/ai", { refreshInterval: 10_000 });
  const [f, setF] = useState<any>(null);
  const [key, setKey] = useState("");
  const [test, setTest] = useState<any>(null);
  const { busy, run } = useAction();
  useEffect(() => {
    if (data && !f) setF({ enabled: data.enabled, provider: data.provider, model: data.model, effort: data.effort,
      ollama_base_url: data.ollama_base_url, ollama_model: data.ollama_model, auto_analyze_new: data.auto_analyze_new });
  }, [data, f]);
  if (error) return <ErrorBox error={error} />;
  if (!data || !f) return <Loading />;
  const save = (patch: any = {}) => run(async () => {
    await api("/admin/ai", { method: "PUT", json: { ...f, ...patch, anthropic_api_key: key || null } });
    setKey("");
    mutate();
  }, "تنظیمات هوش مصنوعی ذخیره شد");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Bot className="h-4 w-4" />اتصال به Claude</CardTitle>
          <CardDescription>وقتی خاموش است یا کلید ندارد، تحلیل قاعده‌محور (بدون مدل) همچنان انجام می‌شود.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center justify-between gap-2 rounded-md border p-3">
            <span><span className="font-medium">تحلیل با مدل فعال باشد</span><span className="block text-xs text-muted-foreground">{f.enabled ? "فعال" : "غیرفعال"}</span></span>
            <Switch checked={f.enabled} onCheckedChange={(v) => { setF({ ...f, enabled: v }); save({ enabled: v }); }} aria-label="فعال/غیرفعال" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label>ارائه‌دهنده</Label>
              <Select value={f.provider} onValueChange={(v) => setF({ ...f, provider: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="claude">Claude (Anthropic API)</SelectItem><SelectItem value="ollama">Ollama محلی</SelectItem></SelectContent>
              </Select></div>
            {f.provider === "claude" ? (
              <div className="space-y-1.5"><Label>مدل</Label>
                <Select value={f.model} onValueChange={(v) => setF({ ...f, model: v })}>
                  <SelectTrigger className="ltr"><SelectValue /></SelectTrigger>
                  <SelectContent>{data.models.map((m: string) => <SelectItem key={m} value={m}><span className="ltr">{m}</span></SelectItem>)}</SelectContent>
                </Select></div>
            ) : (
              <div className="space-y-1.5"><Label>مدل Ollama</Label><Input dir="ltr" value={f.ollama_model} onChange={(e) => setF({ ...f, ollama_model: e.target.value })} /></div>
            )}
          </div>
          {f.provider === "claude" ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="key" className="flex items-center gap-1"><KeyRound className="h-3.5 w-3.5" />Anthropic API Key {data.anthropic_api_key_configured && <Badge variant="good">ثبت شده</Badge>}</Label>
                <Input id="key" type="password" dir="ltr" autoComplete="off" placeholder={data.anthropic_api_key_configured ? "برای تغییر، کلید جدید را وارد کنید" : "sk-ant-..."}
                  value={key} onChange={(e) => setKey(e.target.value)} />
                <p className="text-xs text-muted-foreground">کلید رمزنگاری‌شده در پایگاه داده نگهداری می‌شود و هرگز دوباره نمایش داده نمی‌شود. از console.anthropic.com بگیرید.</p>
              </div>
              <div className="space-y-1.5"><Label>عمق تحلیل (effort)</Label>
                <Select value={f.effort} onValueChange={(v) => setF({ ...f, effort: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="low">low (ارزان‌تر، برای طبقه‌بندی کافی)</SelectItem><SelectItem value="medium">medium</SelectItem><SelectItem value="high">high</SelectItem></SelectContent>
                </Select></div>
            </>
          ) : (
            <div className="space-y-1.5"><Label>آدرس Ollama</Label><Input dir="ltr" value={f.ollama_base_url} onChange={(e) => setF({ ...f, ollama_base_url: e.target.value })} /></div>
          )}
          <label className="flex items-center gap-2 text-sm"><Switch checked={f.auto_analyze_new} onCheckedChange={(v) => setF({ ...f, auto_analyze_new: v })} />تحلیل خودکار آگهی‌های جدید پس از هر جمع‌آوری</label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => save()} disabled={busy}>{busy && <Spinner />}ذخیره</Button>
            <Button variant="outline" disabled={busy} onClick={() => run(() => api("/admin/ai/test", { method: "POST" })).then((r: any) => r && setTest(r))}><PlugZap />تست اتصال</Button>
            {data.anthropic_api_key_configured && f.provider === "claude" && (
              <Button variant="ghost" disabled={busy} onClick={() => { if (confirm("کلید حذف شود؟")) save({ clear_api_key: true }); }}>حذف کلید</Button>
            )}
          </div>
          {test && (test.ok ? <p className="text-sm"><Badge variant="good">متصل</Badge> <bdi className="ltr">{test.model}</bdi></p>
            : <p className="text-sm text-[var(--status-critical)] prose-auto">اتصال ناموفق: {test.error}</p>)}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><RefreshCw className="h-4 w-4" />همگام‌سازی (Sync)</CardTitle>
          <CardDescription>آگهی‌های مرتبطی که هنوز با مدل فعلی تحلیل نشده‌اند یا محتوایشان تغییر کرده به مدل فرستاده می‌شوند.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">آگهی‌های مرتبط</div><div className="num font-semibold">{n(data.relevant_jobs)}</div></div>
            <div className="rounded-md border p-2"><div className="text-xs text-muted-foreground">در انتظار تحلیل مدل</div><div className="num font-semibold">{data.pending === null ? "—" : n(data.pending)}</div></div>
          </div>
          <div>وضعیت همگام‌سازی: <bdi className="ltr text-muted-foreground">{data.sync_status || "—"}</bdi></div>
          <Button disabled={busy || !data.enabled || data.pending === null}
            onClick={() => run(() => api("/admin/ai/sync", { method: "POST", json: { limit: 500 } }), "همگام‌سازی در صف قرار گرفت").then(() => mutate())}>
            <RefreshCw />Sync</Button>
          {!data.enabled && <p className="text-xs text-muted-foreground">برای Sync ابتدا تحلیل با مدل را فعال و کلید را ثبت کنید.</p>}
          <p className="text-xs text-muted-foreground">متن آگهی به‌عنوان داده (نه دستور) به مدل داده می‌شود؛ خروجی با JSON Schema محدود و با Pydantic اعتبارسنجی می‌شود و هر شاهدی که در متن آگهی نباشد حذف می‌شود.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function SmtpTab() {
  const { data, mutate } = useSWR("/admin/smtp");
  const { data: notify, mutate: mutateNotify } = useSWR("/admin/notify");
  const [f, setF] = useState<any>(null);
  const [pw, setPw] = useState("");
  const [nf, setNf] = useState<any>(null);
  const { busy, run } = useAction();
  useEffect(() => { if (data && !f) setF({ ...data }); }, [data, f]);
  useEffect(() => { if (notify && !nf) setNf({ daily_digest_hour: notify.daily_digest_hour, max_per_user_per_hour: notify.max_per_user_per_hour }); }, [notify, nf]);
  if (!f || !nf) return <Loading />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>سرور SMTP</CardTitle><CardDescription>رمز رمزنگاری‌شده ذخیره می‌شود و نمایش داده نمی‌شود.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2 space-y-1.5"><Label>Host</Label><Input dir="ltr" value={f.host || ""} onChange={(e) => setF({ ...f, host: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Port</Label><Input dir="ltr" type="number" value={f.port || 587} onChange={(e) => setF({ ...f, port: Number(e.target.value) })} /></div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label>Username</Label><Input dir="ltr" value={f.username || ""} onChange={(e) => setF({ ...f, username: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Password {f.password_configured && <Badge variant="good">ثبت شده</Badge>}</Label>
              <Input dir="ltr" type="password" autoComplete="off" value={pw} placeholder={f.password_configured ? "بدون تغییر" : ""} onChange={(e) => setPw(e.target.value)} /></div>
          </div>
          <div className="space-y-1.5"><Label>From</Label><Input dir="ltr" value={f.from || ""} placeholder="alerts@example.com" onChange={(e) => setF({ ...f, from: e.target.value })} /></div>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2"><Switch checked={!!f.starttls} onCheckedChange={(v) => setF({ ...f, starttls: v })} />STARTTLS</label>
            <label className="flex items-center gap-2"><Switch checked={!!f.ssl} onCheckedChange={(v) => setF({ ...f, ssl: v })} />SSL/TLS (۴۶۵)</label>
          </div>
          <Button disabled={busy} onClick={() => run(() => api("/admin/smtp", { method: "PUT", json: {
            host: f.host, port: f.port, username: f.username, from: f.from, starttls: !!f.starttls, ssl: !!f.ssl, password: pw || null,
          } }), "تنظیمات SMTP ذخیره شد").then(() => { setPw(""); mutate(); })}>ذخیره</Button>
          <p className="text-xs text-muted-foreground">برای آزمایش: در تب «ایمیل»، نشانی خود را تأیید و «ارسال ایمیل آزمایشی» را بزنید.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>تنظیمات اعلان</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5"><Label>ساعت ارسال گزارش روزانه (به وقت تهران)</Label>
            <Input type="number" min={0} max={23} value={nf.daily_digest_hour} onChange={(e) => setNf({ ...nf, daily_digest_hour: Number(e.target.value) })} /></div>
          <div className="space-y-1.5"><Label>سقف اعلان فوری برای هر کاربر در ساعت</Label>
            <Input type="number" min={1} max={500} value={nf.max_per_user_per_hour} onChange={(e) => setNf({ ...nf, max_per_user_per_hour: Number(e.target.value) })} /></div>
          <Button disabled={busy} onClick={() => run(() => api("/admin/notify", { method: "PUT", json: nf }), "ذخیره شد").then(() => mutateNotify())}>ذخیره</Button>
          <div className="text-xs text-muted-foreground">
            وضعیت ارسال‌ها: {Object.entries(notify?.deliveries || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CollectorTab() {
  const { data, mutate } = useSWR("/admin/collector/settings");
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  return (
    <Card className="max-w-2xl">
      <CardHeader><CardTitle>وضعیت Collector</CardTitle>
        <CardDescription>زمان‌بندی، فعال‌سازی هر منبع و اجرای دستی در صفحه <Link className="text-primary underline" href="/sources">منابع و پوشش</Link>.</CardDescription></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <label className="flex items-center gap-2">
          <Switch checked={!data.paused} onCheckedChange={(v) => run(() => api("/admin/collector/paused", { method: "PUT", json: { paused: !v } }), v ? "جمع‌آوری زمان‌بندی‌شده فعال شد" : "جمع‌آوری متوقف شد").then(() => mutate())} disabled={busy} />
          جمع‌آوری زمان‌بندی‌شده {data.paused ? "متوقف است" : "فعال است"}
        </label>
        {data.sources.map((s: any) => (
          <details key={s.key} className="rounded-md border p-2">
            <summary className="cursor-pointer">{s.key} — هر {n(s.interval_minutes)} دقیقه {s.enabled ? "" : "(غیرفعال)"}</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-2 text-xs ltr">{JSON.stringify(s.config, null, 2)}</pre>
          </details>
        ))}
      </CardContent>
    </Card>
  );
}

function SalaryTab() {
  const { data, mutate } = useSWR("/admin/salary/datasets");
  const fileRef = useRef<HTMLInputElement>(null);
  const [meta, setMeta] = useState({ name: "", source_name: "", source_url: "", data_year: "1405", notes: "" });
  const { busy, run } = useAction();
  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return toast.error("فایل CSV را انتخاب کنید");
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(meta).forEach(([k, v]) => v && fd.append(k, v));
    await run(() => api("/admin/salary/datasets", { method: "POST", body: fd }), "دیتاست بارگذاری و فعال شد");
    mutate();
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Upload className="h-4 w-4" />بارگذاری دیتاست حقوق</CardTitle>
          <CardDescription>فقط داده معتبر و قابل استناد (مثلاً گزارش حقوق ۱۴۰۵). هر بارگذاری با همان نام، نسخه جدید می‌سازد و نسخه قبلی غیرفعال می‌شود.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label>نام دیتاست</Label><Input value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>سال داده (شمسی)</Label><Input type="number" value={meta.data_year} onChange={(e) => setMeta({ ...meta, data_year: e.target.value })} /></div>
          </div>
          <div className="space-y-1.5"><Label>نام منبع</Label><Input value={meta.source_name} onChange={(e) => setMeta({ ...meta, source_name: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>نشانی منبع</Label><Input dir="ltr" value={meta.source_url} onChange={(e) => setMeta({ ...meta, source_url: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>توضیحات</Label><Input value={meta.notes} onChange={(e) => setMeta({ ...meta, notes: e.target.value })} /></div>
          <Input ref={fileRef} type="file" accept=".csv,text/csv" />
          <p className="text-xs text-muted-foreground">ستون‌های CSV (UTF-8): <code className="ltr">{(data?.csv_columns || []).join(",")}</code> — مبالغ ماهانه به تومان؛ category یکی از devops, sre, python, ai_ml, mlops_data.</p>
          <Button disabled={busy || !meta.name || !meta.source_name} onClick={upload}>{busy && <Spinner />}بارگذاری</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Database className="h-4 w-4" />نسخه‌ها</CardTitle></CardHeader>
        <CardContent>
          {!data?.items?.length ? <p className="text-sm text-muted-foreground">هنوز دیتاستی بارگذاری نشده؛ تخمین حقوق فقط از حقوق‌های اعلام‌شده در آگهی‌ها (حداقل ۵ نمونه) انجام می‌شود و در غیر این صورت «نامشخص» است.</p> : (
            <Table>
              <THead><TR><TH>نام</TH><TH>نسخه</TH><TH>سال</TH><TH>ردیف</TH><TH>فعال</TH></TR></THead>
              <TBody>
                {data.items.map((d: any) => (
                  <TR key={d.id}>
                    <TD><bdi>{d.name}</bdi><div className="text-xs text-muted-foreground"><bdi>{d.source_name}</bdi></div></TD>
                    <TD className="num">{n(d.version)}</TD><TD className="num">{n(d.data_year)}</TD><TD className="num">{n(d.row_count)}</TD>
                    <TD><Switch checked={d.is_active} onCheckedChange={(v) => run(() => api(`/admin/salary/datasets/${d.id}`, { method: "PUT", json: { is_active: v } })).then(() => mutate())} /></TD>
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

function UsersTab() {
  const { data, mutate } = useSWR("/admin/users");
  const { data: audit } = useSWR("/admin/audit");
  const { run } = useAction();
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>کاربران</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>ایمیل</TH><TH>نقش</TH><TH>فعال</TH><TH>آخرین ورود</TH></TR></THead>
            <TBody>
              {(data?.items || []).map((u: any) => (
                <TR key={u.id}>
                  <TD className="ltr text-xs">{u.email}</TD>
                  <TD>
                    <Select value={u.role} onValueChange={(role) => run(() => api(`/admin/users/${u.id}`, { method: "PUT", json: { role, is_active: u.is_active } }), "ذخیره شد").then(() => mutate())}>
                      <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="user">کاربر</SelectItem><SelectItem value="admin">مدیر</SelectItem></SelectContent>
                    </Select>
                  </TD>
                  <TD><Switch checked={u.is_active} onCheckedChange={(is_active) => run(() => api(`/admin/users/${u.id}`, { method: "PUT", json: { role: u.role, is_active } }), "ذخیره شد").then(() => mutate())} /></TD>
                  <TD className="text-xs">{dateTime(u.last_login_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" />گزارش رویدادهای امنیتی و مدیریتی</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <THead><TR><TH>زمان</TH><TH>کاربر</TH><TH>رویداد</TH><TH>هدف</TH><TH>IP</TH></TR></THead>
            <TBody>
              {(audit?.items || []).map((a: any) => (
                <TR key={a.id}>
                  <TD className="whitespace-nowrap text-xs">{dateTime(a.created_at)}</TD>
                  <TD className="ltr text-xs">{a.user || "—"}</TD>
                  <TD className="ltr text-xs">{a.action}</TD>
                  <TD className="ltr text-xs">{a.target || ""}</TD>
                  <TD className="ltr text-xs">{a.ip}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  const { data: me } = useMe();
  const admin = me?.role === "admin";
  return (
    <div>
      <PageHeader title="تنظیمات" />
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile"><User />پروفایل</TabsTrigger>
          <TabsTrigger value="email"><Mail />ایمیل</TabsTrigger>
          <TabsTrigger value="telegram"><Send />تلگرام</TabsTrigger>
          {admin && <TabsTrigger value="ai"><Bot />هوش مصنوعی</TabsTrigger>}
          {admin && <TabsTrigger value="smtp"><Mail />SMTP و اعلان</TabsTrigger>}
          {admin && <TabsTrigger value="collector"><RefreshCw />Collector</TabsTrigger>}
          {admin && <TabsTrigger value="salary"><Database />دیتاست حقوق</TabsTrigger>}
          {admin && <TabsTrigger value="users"><Users />کاربران</TabsTrigger>}
        </TabsList>
        <TabsContent value="profile"><ProfileTab /></TabsContent>
        <TabsContent value="email"><EmailTab /></TabsContent>
        <TabsContent value="telegram"><TelegramTab /></TabsContent>
        {admin && <TabsContent value="ai"><AITab /></TabsContent>}
        {admin && <TabsContent value="smtp"><SmtpTab /></TabsContent>}
        {admin && <TabsContent value="collector"><CollectorTab /></TabsContent>}
        {admin && <TabsContent value="salary"><SalaryTab /></TabsContent>}
        {admin && <TabsContent value="users"><UsersTab /></TabsContent>}
      </Tabs>
    </div>
  );
}
