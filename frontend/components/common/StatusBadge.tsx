import { AlertTriangle, CheckCircle2, Circle, Sparkles } from "lucide-react";

export type StatusTone = "new" | "review" | "error" | "resolved" | "normal";

type StatusBadgeProps = {
  tone: StatusTone;
  label: string;
  compact?: boolean;
};

function toneClass(tone: StatusTone): string {
  if (tone === "new") return "border-rose-200 bg-rose-50 text-rose-700";
  if (tone === "review") return "border-amber-200 bg-amber-50 text-amber-800";
  if (tone === "error") return "border-red-200 bg-red-50 text-red-700";
  if (tone === "resolved") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-stone-300 bg-stone-100 text-stone-700";
}

function toneIcon(tone: StatusTone) {
  if (tone === "new") return <Sparkles className="h-3.5 w-3.5" />;
  if (tone === "review") return <AlertTriangle className="h-3.5 w-3.5" />;
  if (tone === "error") return <AlertTriangle className="h-3.5 w-3.5" />;
  if (tone === "resolved") return <CheckCircle2 className="h-3.5 w-3.5" />;
  return <Circle className="h-3.5 w-3.5" />;
}

export function StatusBadge({ tone, label, compact = false }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-semibold leading-none ${toneClass(tone)} ${
        compact ? "text-[10px]" : "text-[11px]"
      }`}
    >
      {toneIcon(tone)}
      {label}
    </span>
  );
}
