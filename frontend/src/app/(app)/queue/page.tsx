import { ListOrdered } from "lucide-react";

export default function QueuePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Hàng đợi tạo media</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Theo dõi tiến độ tất cả tác vụ đang xử lý
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "CPU Queue", value: "0" },
          { label: "GPU Queue", value: "0" },
          { label: "Workers", value: "0" },
          { label: "Completed today", value: "0" },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <p className="text-2xl font-bold">{value}</p>
            <p className="mt-1 text-sm text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>

      {/* Empty state */}
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border bg-card py-20 text-center">
        <ListOrdered className="h-10 w-10 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">Không có tác vụ nào đang chạy</p>
      </div>
    </div>
  );
}
