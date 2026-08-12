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
  first_name: z.string().min(1, "First name is required."),
  last_name: z.string().min(1, "Last name is required."),
  email: z.email("Enter a valid email address."),
  phone: z.string().max(20).optional().or(z.literal("")),
  date_of_birth: z.string().min(1, "Date of birth is required."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

type FormValues = z.infer<typeof schema>;

export function RegisterPage() {
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
      const payload = { ...values, phone: values.phone || undefined };
      const res = await api.post<Envelope<AuthResult>>("/auth/register", payload);
      const result = res.data.data;
      if (result) {
        setAuth(result.user, result.tokens.access_token, result.tokens.refresh_token);
        navigate("/dashboard", { replace: true });
      }
    } catch (error) {
      setServerError(getErrorMessage(error, "Unable to create account."));
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <ShieldCheck className="h-10 w-10 text-indigo-600" />
          <h1 className="text-2xl font-bold text-slate-800">Create your account</h1>
          <p className="text-sm text-slate-500">Join InsureCo to manage your coverage</p>
        </div>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
        >
          {serverError && <Alert message={serverError} />}
          <div className="grid grid-cols-2 gap-4">
            <Field label="First name" htmlFor="first_name" error={errors.first_name?.message}>
              <Input id="first_name" {...register("first_name")} />
            </Field>
            <Field label="Last name" htmlFor="last_name" error={errors.last_name?.message}>
              <Input id="last_name" {...register("last_name")} />
            </Field>
          </div>
          <Field label="Email" htmlFor="email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
          </Field>
          <Field label="Phone (optional)" htmlFor="phone" error={errors.phone?.message}>
            <Input id="phone" type="tel" {...register("phone")} />
          </Field>
          <Field
            label="Date of birth"
            htmlFor="date_of_birth"
            error={errors.date_of_birth?.message}
          >
            <Input id="date_of_birth" type="date" {...register("date_of_birth")} />
          </Field>
          <Field label="Password" htmlFor="password" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              {...register("password")}
            />
          </Field>
          <Button type="submit" loading={isSubmitting}>
            Create account
          </Button>
          <p className="text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-indigo-600 hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
