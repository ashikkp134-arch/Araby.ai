import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import * as authApi from '@/api/auth';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { useAuthStore } from '@/stores/authStore';
import { getErrorMessage } from '@/utils/helpers';

interface SignupForm {
  full_name: string;
  email: string;
  password: string;
}

/**
 * Signup page for creating a new account.
 */
export function SignupPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const [error, setError] = useState('');
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<SignupForm>();

  /**
   * Register the user and enter the workspace hub.
   *
   * @param values - Signup form values.
   */
  async function onSubmit(values: SignupForm) {
    setError('');
    try {
      const tokens = await authApi.signup(values);
      setSession(tokens.user, tokens.access_token);
      navigate('/workspaces', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <div className="glass-panel max-w-md rounded-3xl p-8 shadow-panel animate-rise">
      <h1 className="font-display text-3xl">Create your workspace</h1>
      <p className="mt-2 text-sm text-slate-400">One account across JavaScript, Python, and websites.</p>
      <form className="mt-8 space-y-4" onSubmit={handleSubmit(onSubmit)}>
        <Input label="Full name" {...register('full_name', { required: true })} />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          {...register('email', { required: true })}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          {...register('password', { required: true, minLength: 8 })}
        />
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        <Button type="submit" className="w-full animate-pulseGlow" disabled={isSubmitting}>
          {isSubmitting ? 'Creating…' : 'Create account'}
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-400">
        Already have an account?{' '}
        <Link to="/login" className="text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
