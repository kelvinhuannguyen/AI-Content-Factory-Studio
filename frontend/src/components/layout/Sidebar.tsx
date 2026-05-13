"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  Plus,
  ListOrdered,
  BarChart3,
  Settings,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Tổng quan" },
  { href: "/projects",  icon: FolderOpen,      label: "Dự án" },
  { href: "/queue",     icon: ListOrdered,     label: "Hàng đợi" },
  { href: "/analytics", icon: BarChart3,        label: "Phân tích" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-56 flex-col border-r border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-bg))]">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 px-5 border-b border-[hsl(var(--sidebar-border))]">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary">
          <Sparkles className="h-3.5 w-3.5 text-primary-foreground" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-[13px] font-bold text-foreground">AI Content</span>
          <span className="text-[10px] text-muted-foreground tracking-wide">Factory Studio</span>
        </div>
      </div>

      {/* Create button */}
      <div className="px-3 pt-4 pb-2">
        <Link
          href="/create"
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Tạo mới
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const isActive = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                isActive
                  ? "bg-[hsl(var(--sidebar-item-active))] text-[hsl(var(--sidebar-item-active-text))]"
                  : "text-muted-foreground hover:bg-[hsl(var(--sidebar-item-hover))] hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="border-t border-[hsl(var(--sidebar-border))] px-3 py-3">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
            pathname === "/settings"
              ? "bg-[hsl(var(--sidebar-item-active))] text-[hsl(var(--sidebar-item-active-text))]"
              : "text-muted-foreground hover:bg-[hsl(var(--sidebar-item-hover))] hover:text-foreground"
          )}
        >
          <Settings className="h-4 w-4 shrink-0" />
          Cài đặt
        </Link>
      </div>
    </aside>
  );
}
