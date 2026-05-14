"use client";

import Link from "next/link";
import { Bell, Settings } from "lucide-react";
import { ThemeToggle } from "@/components/shared/ThemeToggle";

export function TopBar() {
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-border/60 bg-card/80 px-6 backdrop-blur-md">
      <div id="topbar-breadcrumb" className="flex items-center gap-2" />

      <div className="flex items-center gap-2">
        <ThemeToggle />

        <button
          className="relative flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          title="Thông báo"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
        </button>

        {/* Avatar — orange gradient in dark, emerald in light */}
        <div className="ml-1 flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/70 text-[11px] font-bold text-primary-foreground select-none">
          AI
        </div>
      </div>
    </header>
  );
}
