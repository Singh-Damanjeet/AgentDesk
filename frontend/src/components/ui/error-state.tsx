import type { ReactNode } from "react";

type ErrorStateProps = {
  title?: string;
  description: string;
  action?: ReactNode;
};

export default function ErrorState({
  title = "Something went wrong",
  description,
  action,
}: ErrorStateProps) {
  return (
    <section
      role="alert"
      className="rounded-xl border border-red-900/70 bg-red-950/20 px-6 py-8"
    >
      <h2 className="text-lg font-medium text-red-200">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-red-300/80">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </section>
  );
}
