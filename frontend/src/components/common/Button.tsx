import type { ButtonHTMLAttributes, PropsWithChildren } from 'react';
import { cn } from '@/utils/helpers';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
}

/**
 * Reusable button with workspace visual variants.
 */
export function Button({
  children,
  className,
  variant = 'primary',
  size = 'md',
  ...props
}: PropsWithChildren<ButtonProps>) {
  const variants = {
    primary: 'bg-accent text-ink-950 hover:bg-accent-soft',
    secondary: 'bg-ink-800 text-sand-50 hover:bg-ink-700 border border-white/10',
    ghost: 'bg-transparent text-sand-50 hover:bg-white/5',
    danger: 'bg-rose-500/90 text-white hover:bg-rose-400',
  };
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2.5 text-sm',
  };

  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:pointer-events-none disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
