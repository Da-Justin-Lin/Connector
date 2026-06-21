import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** Add a hover lift + shadow transition. */
  hover?: boolean;
  /** Show a gradient accent strip along the top edge. */
  accent?: boolean;
};

function cn(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export default function Card({ hover, accent, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "card relative overflow-hidden",
        hover && "card-hover",
        className,
      )}
      {...rest}
    >
      {accent && <span className="absolute inset-x-0 top-0 h-0.5 bg-brand" />}
      {children}
    </div>
  );
}
