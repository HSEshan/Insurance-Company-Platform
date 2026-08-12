import { useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import { Alert, Button, Card, Field, Input, Select } from "../../components/ui";
import type {
  Envelope,
  Meta,
  OpenWorkSummary,
  StaffCreateResult,
  StaffRole,
  User,
} from "../../types";

const STAFF_ROLES: StaffRole[] = ["agent", "adjuster", "manager", "super_admin"];
const PER_PAGE = 50;

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [roleFilter, setRoleFilter] = useState<StaffRole | "">("");
  const [includeInactive, setIncludeInactive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createdCreds, setCreatedCreds] = useState<StaffCreateResult | null>(null);

  const [createForm, setCreateForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    phone: "",
    role: "agent" as StaffRole,
  });

  const [editing, setEditing] = useState<User | null>(null);
  const [editRole, setEditRole] = useState<StaffRole>("agent");
  const [deactivating, setDeactivating] = useState<User | null>(null);
  const [reassignAgentId, setReassignAgentId] = useState("");
  const [reassignAdjusterId, setReassignAdjusterId] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-users", { roleFilter, includeInactive }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<User[]>>("/admin/users", {
        params: {
          page: 1,
          per_page: PER_PAGE,
          role: roleFilter || undefined,
          include_inactive: includeInactive,
        },
      });
      return {
        items: res.data.data ?? [],
        meta: res.data.meta ?? (null as Meta | null),
      };
    },
  });

  const agents = useMemo(
    () =>
      (data?.items ?? []).filter(
        (u) => u.is_active && ["agent", "manager", "super_admin"].includes(u.role),
      ),
    [data?.items],
  );
  const adjusters = useMemo(
    () =>
      (data?.items ?? []).filter(
        (u) =>
          u.is_active && ["adjuster", "manager", "super_admin"].includes(u.role),
      ),
    [data?.items],
  );

  const openWorkQuery = useQuery({
    queryKey: ["admin-open-work", deactivating?.id ?? editing?.id],
    enabled: Boolean(deactivating || (editing && editRole !== editing.role)),
    queryFn: async () => {
      const id = deactivating?.id ?? editing!.id;
      const res = await api.get<Envelope<OpenWorkSummary>>(
        `/admin/users/${id}/open-work`,
      );
      return res.data.data!;
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post<Envelope<StaffCreateResult>>("/admin/users", {
        ...createForm,
        phone: createForm.phone || null,
      });
      return res.data.data!;
    },
    onSuccess: (result) => {
      setCreatedCreds(result);
      setCreateForm({
        email: "",
        first_name: "",
        last_name: "",
        phone: "",
        role: "agent",
      });
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editing) return;
      const res = await api.patch<Envelope<User>>(`/admin/users/${editing.id}`, {
        first_name: editing.first_name,
        last_name: editing.last_name,
        phone: editing.phone,
        role: editRole,
        reassign_agent_id: reassignAgentId || undefined,
        reassign_adjuster_id: reassignAdjusterId || undefined,
      });
      return res.data.data!;
    },
    onSuccess: () => {
      setEditing(null);
      setReassignAgentId("");
      setReassignAdjusterId("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const deactivateMutation = useMutation({
    mutationFn: async () => {
      if (!deactivating) return;
      const res = await api.post<Envelope<User>>(
        `/admin/users/${deactivating.id}/deactivate`,
        {
          reassign_agent_id: reassignAgentId || undefined,
          reassign_adjuster_id: reassignAdjusterId || undefined,
        },
      );
      return res.data.data!;
    },
    onSuccess: () => {
      setDeactivating(null);
      setReassignAgentId("");
      setReassignAdjusterId("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const reactivateMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<Envelope<User>>(`/admin/users/${id}/reactivate`);
      return res.data.data!;
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const resetMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<Envelope<StaffCreateResult>>(
        `/admin/users/${id}/reset-password`,
      );
      return res.data.data!;
    },
    onSuccess: (result) => {
      setCreatedCreds(result);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const work = openWorkQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Staff management</h2>
        <p className="mt-1 text-sm text-slate-500">
          Super Admin only. Staff never self-register — create accounts here and
          issue a temporary password.
        </p>
      </div>

      {error && <Alert message={error} />}

      {createdCreds && (
        <Card className="border-amber-200 bg-amber-50">
          <p className="text-sm font-medium text-amber-900">
            Temporary password for {createdCreds.user.email}
          </p>
          <p className="mt-2 font-mono text-lg text-amber-950">
            {createdCreds.temporary_password}
          </p>
          <p className="mt-1 text-xs text-amber-800">
            {createdCreds.email_sent
              ? "Also sent via email (check MailHog locally)."
              : "Email was not sent — copy this password now; it will not be shown again."}
          </p>
          <Button
            className="mt-3"
            variant="secondary"
            onClick={() => setCreatedCreds(null)}
          >
            Dismiss
          </Button>
        </Card>
      )}

      <Card>
        <h3 className="text-sm font-semibold text-slate-800">Create employee</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Field label="Email" htmlFor="staff-email">
            <Input
              id="staff-email"
              type="email"
              value={createForm.email}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, email: e.target.value }))
              }
            />
          </Field>
          <Field label="Role" htmlFor="staff-role">
            <Select
              id="staff-role"
              value={createForm.role}
              onChange={(e) =>
                setCreateForm((f) => ({
                  ...f,
                  role: e.target.value as StaffRole,
                }))
              }
            >
              {STAFF_ROLES.map((r) => (
                <option key={r} value={r}>
                  {r.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="First name" htmlFor="staff-first">
            <Input
              id="staff-first"
              value={createForm.first_name}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, first_name: e.target.value }))
              }
            />
          </Field>
          <Field label="Last name" htmlFor="staff-last">
            <Input
              id="staff-last"
              value={createForm.last_name}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, last_name: e.target.value }))
              }
            />
          </Field>
          <Field label="Phone (optional)" htmlFor="staff-phone">
            <Input
              id="staff-phone"
              value={createForm.phone}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, phone: e.target.value }))
              }
            />
          </Field>
        </div>
        <Button
          className="mt-4"
          loading={createMutation.isPending}
          onClick={() => createMutation.mutate()}
          disabled={
            !createForm.email ||
            !createForm.first_name ||
            !createForm.last_name
          }
        >
          Create staff account
        </Button>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as StaffRole | "")}
          className="w-48"
        >
          <option value="">All staff roles</option>
          {STAFF_ROLES.map((r) => (
            <option key={r} value={r}>
              {r.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
          />
          Include inactive
        </label>
      </div>

      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-red-600">
                  Could not load staff.
                </td>
              </tr>
            )}
            {data?.items.map((user) => (
              <tr key={user.id}>
                <td className="px-4 py-3 font-medium text-slate-800">
                  {user.first_name} {user.last_name}
                  {user.must_reset_password && (
                    <span className="ml-2 text-xs font-normal text-amber-600">
                      must reset password
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-600">{user.email}</td>
                <td className="px-4 py-3 capitalize">
                  {user.role.replace(/_/g, " ")}
                </td>
                <td className="px-4 py-3">
                  {user.is_active ? (
                    <span className="text-emerald-700">Active</span>
                  ) : (
                    <span className="text-slate-500">Inactive</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="ghost"
                      className="px-2 py-1 text-xs"
                      onClick={() => {
                        setEditing(user);
                        setEditRole(user.role as StaffRole);
                        setDeactivating(null);
                        setReassignAgentId("");
                        setReassignAdjusterId("");
                      }}
                    >
                      Edit
                    </Button>
                    {user.is_active ? (
                      <>
                        <Button
                          variant="ghost"
                          className="px-2 py-1 text-xs"
                          onClick={() => resetMutation.mutate(user.id)}
                          loading={resetMutation.isPending}
                        >
                          Reset pwd
                        </Button>
                        <Button
                          variant="ghost"
                          className="px-2 py-1 text-xs text-red-600"
                          onClick={() => {
                            setDeactivating(user);
                            setEditing(null);
                            setReassignAgentId("");
                            setReassignAdjusterId("");
                          }}
                        >
                          Deactivate
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="ghost"
                        className="px-2 py-1 text-xs"
                        onClick={() => reactivateMutation.mutate(user.id)}
                        loading={reactivateMutation.isPending}
                      >
                        Reactivate
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {editing && (
        <Card>
          <h3 className="text-sm font-semibold text-slate-800">
            Edit {editing.first_name} {editing.last_name}
          </h3>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Field label="First name" htmlFor="edit-first">
              <Input
                id="edit-first"
                value={editing.first_name}
                onChange={(e) =>
                  setEditing({ ...editing, first_name: e.target.value })
                }
              />
            </Field>
            <Field label="Last name" htmlFor="edit-last">
              <Input
                id="edit-last"
                value={editing.last_name}
                onChange={(e) =>
                  setEditing({ ...editing, last_name: e.target.value })
                }
              />
            </Field>
            <Field label="Phone" htmlFor="edit-phone">
              <Input
                id="edit-phone"
                value={editing.phone ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, phone: e.target.value })
                }
              />
            </Field>
            <Field label="Role" htmlFor="edit-role">
              <Select
                id="edit-role"
                value={editRole}
                onChange={(e) => setEditRole(e.target.value as StaffRole)}
              >
                {STAFF_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {editRole !== editing.role && work && (
            <ReassignFields
              work={work}
              excludeId={editing.id}
              agents={agents}
              adjusters={adjusters}
              reassignAgentId={reassignAgentId}
              reassignAdjusterId={reassignAdjusterId}
              setReassignAgentId={setReassignAgentId}
              setReassignAdjusterId={setReassignAdjusterId}
            />
          )}
          <div className="mt-4 flex gap-2">
            <Button
              loading={updateMutation.isPending}
              onClick={() => updateMutation.mutate()}
            >
              Save changes
            </Button>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {deactivating && (
        <Card className="border-red-200">
          <h3 className="text-sm font-semibold text-slate-800">
            Deactivate {deactivating.first_name} {deactivating.last_name}?
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Open work must be reassigned before deactivation when required.
          </p>
          {work && (
            <ReassignFields
              work={work}
              excludeId={deactivating.id}
              agents={agents}
              adjusters={adjusters}
              reassignAgentId={reassignAgentId}
              reassignAdjusterId={reassignAdjusterId}
              setReassignAgentId={setReassignAgentId}
              setReassignAdjusterId={setReassignAdjusterId}
            />
          )}
          <div className="mt-4 flex gap-2">
            <Button
              variant="danger"
              loading={deactivateMutation.isPending}
              onClick={() => deactivateMutation.mutate()}
            >
              Confirm deactivate
            </Button>
            <Button variant="secondary" onClick={() => setDeactivating(null)}>
              Cancel
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function ReassignFields({
  work,
  excludeId,
  agents,
  adjusters,
  reassignAgentId,
  reassignAdjusterId,
  setReassignAgentId,
  setReassignAdjusterId,
}: {
  work: OpenWorkSummary;
  excludeId: string;
  agents: User[];
  adjusters: User[];
  reassignAgentId: string;
  reassignAdjusterId: string;
  setReassignAgentId: (v: string) => void;
  setReassignAdjusterId: (v: string) => void;
}) {
  return (
    <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs text-slate-600">
        Open work: {work.policies} polic{work.policies === 1 ? "y" : "ies"},{" "}
        {work.open_claims} open claim{work.open_claims === 1 ? "" : "s"}.
      </p>
      {work.requires_agent_reassign && (
        <Field label="Reassign policies to" htmlFor="reassign-agent">
          <Select
            id="reassign-agent"
            value={reassignAgentId}
            onChange={(e) => setReassignAgentId(e.target.value)}
          >
            <option value="">Select agent…</option>
            {agents
              .filter((u) => u.id !== excludeId)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.first_name} {u.last_name} ({u.role.replace(/_/g, " ")})
                </option>
              ))}
          </Select>
        </Field>
      )}
      {work.requires_adjuster_reassign && (
        <Field label="Reassign claims to" htmlFor="reassign-adjuster">
          <Select
            id="reassign-adjuster"
            value={reassignAdjusterId}
            onChange={(e) => setReassignAdjusterId(e.target.value)}
          >
            <option value="">Select adjuster…</option>
            {adjusters
              .filter((u) => u.id !== excludeId)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.first_name} {u.last_name} ({u.role.replace(/_/g, " ")})
                </option>
              ))}
          </Select>
        </Field>
      )}
      {!work.requires_agent_reassign && !work.requires_adjuster_reassign && (
        <p className="text-xs text-emerald-700">No reassignment required.</p>
      )}
    </div>
  );
}
