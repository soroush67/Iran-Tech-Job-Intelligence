"use client";
import { ThemeProvider } from "next-themes";
import { SWRConfig } from "swr";
import { fetcher } from "@/lib/api";
import { ToastHost } from "@/components/toast";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <SWRConfig value={{ fetcher, revalidateOnFocus: false, shouldRetryOnError: false }}>
        {children}
        <ToastHost />
      </SWRConfig>
    </ThemeProvider>
  );
}
