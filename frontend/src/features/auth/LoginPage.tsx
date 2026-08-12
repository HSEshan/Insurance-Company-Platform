import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Alert, Button, Field, Input } from "../../components/ui";
import type { AuthResult, Envelope } from "../../types";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const res = await api.post<Envelope<AuthResult>>("/auth/login", values);
      const result = res.data.data;
      if (result) {
        setAuth(result.user, result.tokens.access_token, result.tokens.refresh_token);
        navigate(
          result.user.must_reset_password ? "/change-password" : "/dashboard",
          { replace: true },
        );
      }
    } catch (error) {
      setServerError(getErrorMessage(error, "Unable to sign in."));
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <ShieldCheck className="h-10 w-10 text-indigo-600" />
          <h1 className="text-2xl font-bold text-slate-800">Welcome back</h1>
          <p className="text-sm text-slate-500">Sign in to your InsureCo account</p>
        </div>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
        >
          {serverError && <Alert message={serverError} />}
          <Field label="Email" htmlFor="email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
          </Field>
          <Field label="Password" htmlFor="password" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
            />
          </Field>
          <Button type="submit" loading={isSubmitting}>
            Sign in
          </Button>
          <p className="text-center text-sm text-slate-500">
            Don&apos;t have an account?{" "}
            <Link to="/register" className="font-medium text-indigo-600 hover:underline">
              Register
            </Link>
          </p>
          <p className="text-center text-sm text-slate-500">
            <Link to="/" className="font-medium text-indigo-600 hover:underline">
              ← Back to landing
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
