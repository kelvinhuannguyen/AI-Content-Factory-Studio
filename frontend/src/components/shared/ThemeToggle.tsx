"use client";

import { useTheme } from "next-themes";
import { Moon, Sun, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  const options = [
    { value: "light",  icon: Sun,     label: "Sáng" },
    { value: "system", icon: Monitor, label: "Hệ thống" },
    { value: "dark",   icon: Moon,    label: "Tối" },
  ] as const;

  return (
    <div className={cn("flex items-center gap-0.5 rounded-xl bg-muted p-1", className)}>
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          title={label}
          className={cn(
            "flex h-6 w-6 items-center justify-center rounded-lg transition-all",
            theme === value
              ? "bg-card card-shadow text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="h-3 w-3" />
        </button>
      ))}
    </div>
  );
}
