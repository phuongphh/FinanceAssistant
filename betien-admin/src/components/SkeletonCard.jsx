export default function SkeletonCard({ className = '' }) {
  return (
    <div className={`animate-pulse rounded-2xl border border-hairline bg-porcelain p-5 ${className}`}>
      <div className="h-3 w-20 rounded-full bg-ink-100" />
      <div className="mt-5 h-9 w-28 rounded-full bg-ink-100" />
      <div className="mt-4 h-3 w-full rounded-full bg-ink-100" />
    </div>
  );
}
