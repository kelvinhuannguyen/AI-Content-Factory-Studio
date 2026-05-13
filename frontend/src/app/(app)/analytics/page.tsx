import { BarChart3 } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Phân tích</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Thống kê hiệu suất YouTube và nội dung
        </p>
      </div>
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border bg-card py-20 text-center">
        <BarChart3 className="h-10 w-10 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          Kết nối YouTube để xem thống kê (Phase 2)
        </p>
      </div>
    </div>
  );
}
