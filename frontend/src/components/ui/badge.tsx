import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      default: "border-transparent bg-primary/10 text-primary",
      secondary: "border-transparent bg-secondary text-secondary-foreground",
      outline: "text-foreground",
      good: "border-transparent bg-[color-mix(in_oklab,var(--status-good)_15%,transparent)] text-foreground",
      warning: "border-transparent bg-[color-mix(in_oklab,var(--status-warning)_22%,transparent)] text-foreground",
      critical: "border-transparent bg-[color-mix(in_oklab,var(--status-critical)_15%,transparent)] text-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
