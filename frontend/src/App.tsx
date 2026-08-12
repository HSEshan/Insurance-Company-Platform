import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./features/auth/LoginPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { ChangePasswordPage } from "./features/auth/ChangePasswordPage";
import { AdminUsersPage } from "./features/admin/AdminUsersPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { ProfilePage } from "./features/profile/ProfilePage";
import { CustomersPage } from "./features/customers/CustomersPage";
import { QuotesPage } from "./features/quotes/QuotesPage";
import { QuoteDetailPage } from "./features/quotes/QuoteDetailPage";
import { QuoteWizardPage } from "./features/quotes/QuoteWizardPage";
import { PoliciesPage } from "./features/policies/PoliciesPage";
import { PolicyDetailPage } from "./features/policies/PolicyDetailPage";
import { ClaimsPage } from "./features/claims/ClaimsPage";
import { ClaimDetailPage } from "./features/claims/ClaimDetailPage";
import { ClaimSubmitPage } from "./features/claims/ClaimSubmitPage";
import { PaymentsPage } from "./features/payments/PaymentsPage";
import { NotificationsPage } from "./features/notifications/NotificationsPage";
import { AuditPage } from "./features/audit/AuditPage";
import { ReportsPage } from "./features/reports/ReportsPage";
import { LandingPage } from "./features/landing/LandingPage";
import { NotFoundPage } from "./features/NotFoundPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={<ProtectedRoute />}
      >
        <Route path="/change-password" element={<ChangePasswordPage />} />
      </Route>

      <Route element={<ProtectedRoute roles={["super_admin"]} />}>
        <Route element={<AppLayout />}>
          <Route path="/admin" element={<AdminUsersPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
        </Route>
      </Route>

      <Route
        element={
          <ProtectedRoute roles={["customer", "agent", "super_admin"]} />
        }
      >
        <Route element={<AppLayout />}>
          <Route path="/quotes/new" element={<QuoteWizardPage />} />
          <Route path="/claims/new" element={<ClaimSubmitPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={["agent", "manager", "super_admin"]} />}>
        <Route element={<AppLayout />}>
          <Route path="/customers" element={<CustomersPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute roles={["manager", "super_admin"]} />}>
        <Route element={<AppLayout />}>
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Route>
      </Route>

      {/* Adjusters work claims, not billing (specs §4 permission matrix). */}
      <Route
        element={
          <ProtectedRoute
            roles={["customer", "agent", "manager", "super_admin"]}
          />
        }
      >
        <Route element={<AppLayout />}>
          <Route path="/payments" element={<PaymentsPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/quotes" element={<QuotesPage />} />
          <Route path="/quotes/:id" element={<QuoteDetailPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/policies/:id" element={<PolicyDetailPage />} />
          <Route path="/claims" element={<ClaimsPage />} />
          <Route path="/claims/:id" element={<ClaimDetailPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
