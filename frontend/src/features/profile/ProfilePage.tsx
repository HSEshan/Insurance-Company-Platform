import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Badge, Card } from "../../components/ui";
import type { Customer, Envelope } from "../../types";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between border-b border-slate-100 py-2 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value ?? "—"}</span>
    </div>
  );
}

export function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const isCustomer = user?.role === "customer";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["my-customer-profile"],
    enabled: isCustomer,
    queryFn: async () => {
      const res = await api.get<Envelope<Customer>>("/customers/me");
      return res.data.data;
    },
  });

  if (!user) return null;

  return (
    <div className="max-w-2xl space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">My Profile</h2>

      <Card>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
          Account
        </h3>
        <Row label="Name" value={`${user.first_name} ${user.last_name}`} />
        <Row label="Email" value={user.email} />
        <Row label="Phone" value={user.phone} />
        <Row
          label="Role"
          value={<span className="capitalize">{user.role.replace(/_/g, " ")}</span>}
        />
      </Card>

      {isCustomer && (
        <Card>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Customer Details
          </h3>
          {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {isError && (
            <p className="text-sm text-red-600">Could not load your profile.</p>
          )}
          {data && (
            <>
              <Row label="Date of Birth" value={data.date_of_birth} />
              <Row label="SSN" value={data.ssn_masked} />
              <Row label="Driver's License" value={data.dl_number} />
              <Row
                label="Address"
                value={
                  data.address_line1
                    ? `${data.address_line1}, ${data.city ?? ""} ${data.state ?? ""}`
                    : null
                }
              />
              <Row label="Risk Tier" value={<Badge value={data.risk_tier} />} />
            </>
          )}
        </Card>
      )}
    </div>
  );
}
