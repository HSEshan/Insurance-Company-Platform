import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  BarChart3,
  ClipboardList,
  CreditCard,
  FileText,
  LayoutDashboard,
  LogOut,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  UserCircle,
  Users,
} from "lucide-react";
import { useAuthStore } from "../../stores/authStore";
import { api, getErrorMessage } from "../../lib/api";
import { NotificationBell } from "../../features/notifications/NotificationBell";
import type { UserRole } from "../../types";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  roles?: UserRole[];
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    to: "/quotes",
    label: "Quotes",
    icon: FileText,
    roles: ["customer", "agent", "manager", "super_admin"],
  },
  {
    to: "/policies",
    label: "Policies",
    icon: Shield,
    roles: ["customer", "agent", "adjuster", "manager", "super_admin"],
  },
  {
    to: "/claims",
    label: "Claims",
    icon: ClipboardList,
    roles: ["customer", "agent", "adjuster", "manager", "super_admin"],
  },
  {
    to: "/payments",
    label: "Payments",
    icon: CreditCard,
    roles: ["customer", "agent", "manager", "super_admin"],
  },
  {
    to: "/customers",
    label: "Customers",
    icon: Users,
    roles: ["agent", "manager", "super_admin"],
  },
  {
    to: "/reports",
    label: "Reports",
    icon: BarChart3,
    roles: ["manager", "super_admin"],
  },
  {
    to: "/audit",
    label: "Audit log",
    icon: ScrollText,
    roles: ["manager", "super_admin"],
  },
  {
    to: "/admin",
    label: "Staff admin",
    icon: Settings,
    roles: ["super_admin"],
  },
  { to: "/profile", label: "My Profile", icon: UserCircle },
];

export function AppLayout() {
  const { user, clearAuth } = useAuthStore();
  const navigate = useNavigate();

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role)),
  );

  async function handleLogout() {
    try {
      await api.post("/auth/logout");
    } catch (error) {
      // Logout is best-effort; clear local state regardless.
      console.warn(getErrorMessage(error));
    }
    clearAuth();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-col bg-slate-900 text-slate-100">
        <div className="flex items-center gap-2 px-6 py-5 text-lg font-semibold">
          <ShieldCheck className="h-6 w-6 text-indigo-400" />
          <span>InsureCo</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {visibleItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-slate-300 hover:bg-slate-800"
                }`
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-6 py-4 text-sm text-slate-300 hover:bg-slate-800"
        >
          <LogOut className="h-5 w-5" />
          Sign out
        </button>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-8 py-4">
          <h1 className="text-lg font-semibold text-slate-800">
            Insurance Management Platform
          </h1>
          {user && (
            <div className="flex items-center gap-4">
              <NotificationBell />
              <div className="text-right">
                <p className="text-sm font-medium text-slate-800">
                  {user.first_name} {user.last_name}
                </p>
                <p className="text-xs capitalize text-slate-500">
                  {user.role.replace(/_/g, " ")}
                </p>
              </div>
            </div>
          )}
        </header>
        <main className="flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
