import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variantClasses: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500",
  secondary:
    "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 focus:ring-indigo-500",
  danger: "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100 focus:ring-slate-400",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

export function Button({
  variant = "primary",
  loading = false,
  disabled,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 ${variantClasses[variant]} ${className}`}
      {...rest}
    >
      {loading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  children: ReactNode;
}

export function Field({ label, htmlFor, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 ${props.className ?? ""}`}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 ${props.className ?? ""}`}
    />
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-6 shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function Alert({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </div>
  );
}

const badgeColors: Record<string, string> = {
  // Risk tiers
  preferred: "bg-emerald-100 text-emerald-700",
  standard: "bg-blue-100 text-blue-700",
  substandard: "bg-amber-100 text-amber-700",
  declined: "bg-red-100 text-red-700",
  // Quote / policy / endorsement statuses
  draft: "bg-slate-100 text-slate-600",
  pending: "bg-amber-100 text-amber-700",
  pending_review: "bg-amber-100 text-amber-700",
  under_review: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  active: "bg-emerald-100 text-emerald-700",
  bound: "bg-indigo-100 text-indigo-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-red-100 text-red-700",
  lapsed: "bg-orange-100 text-orange-700",
  expired: "bg-slate-100 text-slate-500",
  upcoming: "bg-slate-100 text-slate-600",
  due: "bg-amber-100 text-amber-700",
  paid: "bg-emerald-100 text-emerald-700",
  overdue: "bg-red-100 text-red-700",
  waived: "bg-slate-100 text-slate-500",
  // Payments
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  voided: "bg-slate-100 text-slate-500",
  refunded: "bg-amber-100 text-amber-700",
  premium: "bg-blue-100 text-blue-700",
  claim_payout: "bg-purple-100 text-purple-700",
  // Claims
  submitted: "bg-blue-100 text-blue-700",
  assigned: "bg-indigo-100 text-indigo-700",
  investigating: "bg-amber-100 text-amber-700",
  info_requested: "bg-orange-100 text-orange-700",
  disputed: "bg-purple-100 text-purple-700",
};

export function Badge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const color = badgeColors[value] ?? "bg-slate-100 text-slate-600";
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${color}`}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}
