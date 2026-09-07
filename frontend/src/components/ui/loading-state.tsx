type LoadingStateProps = {
  label?: string;
};

export default function LoadingState({
  label = "Loading...",
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-8 text-sm text-zinc-400"
    >
      <span className="inline-flex items-center gap-3">
        <span
          aria-hidden="true"
          className="h-2 w-2 animate-pulse rounded-full bg-zinc-400"
        />
        {label}
      </span>
    </div>
  );
}
