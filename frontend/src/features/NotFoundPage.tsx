import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-100">
      <h1 className="text-5xl font-bold text-slate-800">404</h1>
      <p className="text-slate-500">This page could not be found.</p>
      <Link to="/dashboard" className="font-medium text-indigo-600 hover:underline">
        Back to dashboard
      </Link>
    </div>
  );
}
