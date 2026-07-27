import { forwardRef } from 'react';
import type { InputHTMLAttributes } from 'react';
import { cn } from '@/utils/helpers';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

/**
 * Labeled text input used across auth and project forms.
 *
 * Wrapped in `forwardRef` so libraries like react-hook-form (which attach a
 * `ref` via `register()`) can read and control the underlying DOM input.
 * Without this, the ref is silently dropped and form values can never be
 * read, causing submissions to fail validation with no visible error.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, className, id, ...props },
  ref,
) {
  const inputId = id || props.name;
  return (
    <label className="flex w-full flex-col gap-1.5 text-sm">
      {label ? <span className="font-medium text-slate-200">{label}</span> : null}
      <input
        ref={ref}
        id={inputId}
        className={cn(
          'rounded-lg border border-white/10 bg-ink-900/80 px-3 py-2.5 text-sand-50 outline-none transition placeholder:text-slate-500 focus:border-accent/60 focus:ring-2 focus:ring-accent/20',
          className,
        )}
        {...props}
      />
      {error ? <span className="text-xs text-rose-300">{error}</span> : null}
    </label>
  );
});
