type SkeletonProps = {
  className?: string;
};

// Shimmering placeholder block. Compose several to mirror a card's layout
// while data loads.
export default function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`relative overflow-hidden rounded-md bg-surface-2 ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-content/10 to-transparent" />
    </div>
  );
}
