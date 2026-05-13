import { Settings, Key, Bell, Globe } from "lucide-react";

const API_KEYS = [
  { id: "kymaapi", label: "KymaAPI", desc: "AI gateway chính (GPT-4o, video, image)" },
  { id: "elevenlabs", label: "ElevenLabs", desc: "Text-to-Speech giọng đọc" },
  { id: "suno", label: "Suno AI", desc: "Tạo nhạc cho MV" },
  { id: "youtube", label: "YouTube", desc: "Đăng video lên kênh YouTube" },
  { id: "telegram", label: "Telegram Bot", desc: "Thông báo duyệt qua Telegram" },
];

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Cài đặt</h1>
        <p className="mt-1 text-sm text-muted-foreground">Quản lý API keys và tùy chọn hệ thống</p>
      </div>

      {/* API Keys */}
      <section className="rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-6 py-4">
          <Key className="h-4 w-4 text-primary" />
          <h2 className="font-semibold">API Keys</h2>
        </div>
        <div className="divide-y divide-border">
          {API_KEYS.map(({ id, label, desc }) => (
            <div key={id} className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm font-medium">{label}</p>
                <p className="text-xs text-muted-foreground">{desc}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
                  Chưa cấu hình
                </span>
                <button className="rounded-md bg-secondary px-3 py-1.5 text-xs font-medium hover:bg-secondary/80 transition-colors">
                  Cài đặt
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Notifications */}
      <section className="rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-6 py-4">
          <Bell className="h-4 w-4 text-primary" />
          <h2 className="font-semibold">Thông báo duyệt</h2>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Email (Gmail)</p>
              <p className="text-xs text-muted-foreground">kelvinhuannguyen@gmail.com</p>
            </div>
            <div className="h-4 w-8 rounded-full bg-muted" />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Telegram Bot</p>
              <p className="text-xs text-muted-foreground">Nhận nút duyệt trực tiếp trên Telegram</p>
            </div>
            <div className="h-4 w-8 rounded-full bg-muted" />
          </div>
        </div>
      </section>

      {/* Language */}
      <section className="rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-6 py-4">
          <Globe className="h-4 w-4 text-primary" />
          <h2 className="font-semibold">Ngôn ngữ</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 p-6">
          {[
            { code: "vi", label: "Tiếng Việt", flag: "🇻🇳", active: true },
            { code: "en", label: "English", flag: "🇺🇸", active: false },
          ].map(({ code, label, flag, active }) => (
            <button
              key={code}
              className={`flex items-center gap-3 rounded-lg border p-3 text-sm transition-colors ${
                active
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border hover:border-primary/50 hover:bg-muted"
              }`}
            >
              <span className="text-lg">{flag}</span>
              <span className="font-medium">{label}</span>
              {active && (
                <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
