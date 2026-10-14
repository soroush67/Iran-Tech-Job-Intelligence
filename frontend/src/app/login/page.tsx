"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Radar } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/common";
import { ThemeToggle } from "@/components/theme-toggle";

function LoginForm() {
  const params = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (mode === "login") await api("/auth/login", { method: "POST", json: { email, password } });
      else await api("/auth/register", { method: "POST", json: { email, password, display_name: name || null } });
      const next = params.get("next");
      window.location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Radar className="h-5 w-5 text-primary" />
          <CardTitle>Iran Tech Job Intelligence</CardTitle>
        </div>
        <CardDescription>{mode === "login" ? "ورود به داشبورد" : "ساخت حساب کاربری"}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && (
            <div className="space-y-1.5">
              <Label htmlFor="name">نام نمایشی</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="email">ایمیل</Label>
            <Input id="email" type="email" dir="ltr" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">رمز عبور</Label>
            <Input id="password" type="password" dir="ltr" required minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"} value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          {err && <p className="prose-auto text-sm text-[var(--status-critical)]" role="alert">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy && <Spinner />}
            {mode === "login" ? "ورود" : "ثبت‌نام"}
          </Button>
          <button type="button" className="w-full text-center text-sm text-primary hover:underline"
            onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "حساب ندارید؟ ثبت‌نام" : "حساب دارید؟ ورود"}
          </button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center p-4">
      <div className="absolute left-4 top-4"><ThemeToggle /></div>
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
