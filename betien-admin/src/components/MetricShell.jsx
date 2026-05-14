export default function MetricShell({ title, eyebrow, children }) {
  return (
    <section className="rounded-3xl border border-hairline bg-porcelain p-5">
      <div className="mb-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">{eyebrow}</p>
        <h2 className="mt-1 font-display text-xl font-medium text-ink-900">{title}</h2>
      </div>
      {children}
    </section>
  );
}
