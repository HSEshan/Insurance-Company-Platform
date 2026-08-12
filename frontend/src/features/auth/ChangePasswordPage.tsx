import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Navigate, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Alert, Button, Field, Input } from "../../components/ui";
import type { Envelope, User } from "../../types";

const schema = z
  .object({
    current_password: z.string().min(1, "Current password is required."),
    new_password: z.string().min(8, "Use at least 8 characters."),
    confirm_password: z.string().min(1, "Confirm your new password."),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  });

type FormValues = z.infer<typeof schema>;

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const { user, setUser, isAuthenticated } = useAuthStore();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      const res = await api.post<Envelope<User>>("/auth/change-password", {
        current_password: values.current_password,
        new_password: values.new_password,
      });
      if (res.data.data) {
        setUser(res.data.data);
      }
      navigate("/dashboard", { replace: true });
    } catch (error) {
      setServerError(getErrorMessage(error, "Unable to change password."));
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2">
          <ShieldCheck className="h-10 w-10 text-indigo-600" />
          <h1 className="text-2xl font-bold text-slate-800">Set a new password</h1>
          <p className="text-center text-sm text-slate-500">
            {user.must_reset_password
              ? "Your temporary password must be changed before continuing."
              : "Update the password for your InsureCo account."}
          </p>
        </div>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
        >
          {serverError && <Alert message={serverError} />}
          <Field
            label="Current password"
            htmlFor="current_password"
            error={errors.current_password?.message}
          >
            <Input
              id="current_password"
              type="password"
              autoComplete="current-password"
              {...register("current_password")}
            />
          </Field>
          <Field
            label="New password"
            htmlFor="new_password"
            error={errors.new_password?.message}
          >
            <Input
              id="new_password"
              type="password"
              autoComplete="new-password"
              {...register("new_password")}
            />
          </Field>
          <Field
            label="Confirm new password"
            htmlFor="confirm_password"
            error={errors.confirm_password?.message}
          >
            <Input
              id="confirm_password"
              type="password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
          </Field>
          <Button type="submit" loading={isSubmitting}>
            Save password
          </Button>
        </form>
      </div>
    </div>
  );
}
