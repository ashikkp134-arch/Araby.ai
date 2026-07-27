import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import * as authApi from '@/api/auth';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { useAuthStore } from '@/stores/authStore';
import { getErrorMessage } from '@/utils/helpers';

interface LoginForm {
  email: string;
  password: string;
}

/**
 * Login page with email/password authentication.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const [error, setError] = useState('');
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<LoginForm>();

  /**
   * Authenticate the user and enter the workspace hub.
   *
   * @param values - Login form values.
   */
  async function onSubmit(values: LoginForm) {
    setError('');
    try {
      const tokens = await authApi.login(values);
      setSession(tokens.user, tokens.access_token);
      // Replace history so back-button does not return to the login form.
      navigate('/workspaces', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return (
    <div className="glass-panel max-w-md rounded-3xl p-8 shadow-panel animate-rise">
      <h1 className="font-display text-3xl">Welcome back</h1>
      <p className="mt-2 text-sm text-slate-400">Sign in to continue building with AI.</p>
      <form className="mt-8 space-y-4" onSubmit={handleSubmit(onSubmit)}>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          {...register('email', { required: true })}
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          {...register('password', { required: true, minLength: 8 })}
        />
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-400">
        New here?{' '}
        <Link to="/signup" className="text-accent hover:underline">
          Create an account
        </Link>
      </p>
    </div>
  );
}
