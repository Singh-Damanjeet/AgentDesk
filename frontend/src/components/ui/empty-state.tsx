import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description: string;
  action?: ReactNode;
};

export default function EmptyState({
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <section className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/30 px-6 py-12 text-center">
      <h2 className="text-lg font-medium text-zinc-200">{title}</h2>
      <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-zinc-500">
        {description}
      </p>
      {action && <div className="mt-6">{action}</div>}
    </section>
  );
}
