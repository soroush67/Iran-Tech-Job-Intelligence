"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import {
  BarChart3, Bell, Briefcase, Building2, LayoutDashboard, LogOut, Menu, Radar, Settings, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV = [
  { href: "/", label: "داشبورد", icon: LayoutDashboard },
  { href: "/jobs", label: "آگهی‌ها", icon: Briefcase },
  { href: "/companies", label: "شرکت‌ها", icon: Building2 },
  { href: "/insights", label: "تحلیل بازار", icon: BarChart3 },
  { href: "/alerts", label: "جست‌وجوها و هشدارها", icon: Bell },
  { href: "/sources", label: "منابع و پوشش", icon: Radar },
  { href: "/settings", label: "تنظیمات", icon: Settings },
];

export type Me = {
  id: number; email: string; display_name: string | null; role: "admin" | "user";
  profile: any; notify_email: string | null; notify_email_verified: boolean;
  telegram: { status: string; username: string | null } | null;
};

export function useMe() {
  return useSWR<Me>("/auth/me");
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const nav = (
    <nav className="flex flex-col gap-1 p-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-e bg-card lg:block">
        <div className="flex h-14 items-center gap-2 border-b px-4">
          <Radar className="h-5 w-5 text-primary" />
          <span className="text-sm font-bold">Iran Tech Job Intelligence</span>
        </div>
        {nav}
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 right-0 w-64 bg-card shadow-xl">
            <div className="flex h-14 items-center justify-between border-b px-4">
              <span className="text-sm font-bold">منو</span>
              <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="بستن منو">
                <X />
              </Button>
            </div>
            {nav}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-card/90 px-4 backdrop-blur">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label="باز کردن منو">
            <Menu />
          </Button>
          <div className="flex-1" />
          <ThemeToggle />
          {me && (
            <span className="hidden text-sm text-muted-foreground sm:inline">
              <bdi>{me.display_name || me.email}</bdi>
              {me.role === "admin" && <span className="ms-1 rounded bg-primary/10 px-1.5 text-xs text-primary">مدیر</span>}
            </span>
          )}
          <Button variant="ghost" size="icon" onClick={logout} aria-label="خروج">
            <LogOut />
          </Button>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
