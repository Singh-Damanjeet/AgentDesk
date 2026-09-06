type EmptyStateProps = {
  title: string;
  description: string;
};

export default function EmptyState({
  title,
  description,
}: EmptyStateProps) {
  return (
    <section className="rounded-xl border border-dashed border-zinc-700 bg-zinc-900/30 px-6 py-12 text-center">
      <h2 className="text-lg font-medium text-zinc-200">{title}</h2>
      <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-zinc-500">
        {description}
      </p>
    </section>
  );
}
