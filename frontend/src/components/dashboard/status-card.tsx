export type StatusCardTone = "success" | "neutral" | "warning";

type StatusCardProps = {
  label: string;
  value: string;
  description: string;
  tone?: StatusCardTone;
};

const toneClasses: Record<StatusCardTone, string> = {
  success: "border-emerald-900/70 bg-emerald-950/20 text-emerald-300",
  neutral: "border-zinc-800 bg-zinc-900/60 text-zinc-200",
  warning: "border-amber-900/70 bg-amber-950/20 text-amber-300",
};

export default function StatusCard({
  label,
  value,
  description,
  tone = "neutral",
}: StatusCardProps) {
  return (
    <article className={`rounded-xl border p-5 ${toneClasses[tone]}`}>
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-zinc-300">{label}</p>
        <span
          aria-hidden="true"
          className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
            tone === "success"
              ? "bg-emerald-400"
              : tone === "warning"
                ? "bg-amber-400"
                : "bg-zinc-500"
          }`}
        />
      </div>
      <p className="mt-7 text-2xl font-semibold tracking-tight text-white">
        {value}
      </p>
      <p className="mt-2 text-sm leading-5 text-zinc-500">{description}</p>
    </article>
  );
}
