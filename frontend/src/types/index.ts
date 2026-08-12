export type UserRole =
  | "customer"
  | "agent"
  | "adjuster"
  | "manager"
  | "super_admin";

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string | null;
  role: UserRole;
  is_active: boolean;
  must_reset_password?: boolean;
  last_login?: string | null;
  created_at: string;
}

export type StaffRole = Exclude<UserRole, "customer">;

export interface StaffCreateResult {
  user: User;
  temporary_password: string;
  email_sent: boolean;
}

export interface OpenWorkSummary {
  policies: number;
  open_claims: number;
  requires_agent_reassign: boolean;
  requires_adjuster_reassign: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResult {
  user: User;
  tokens: TokenPair;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface Meta {
  page: number;
  per_page: number;
  total: number;
}

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  meta?: Meta | null;
  error: ApiErrorDetail | null;
}

export interface Customer {
  id: string;
  user_id: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  date_of_birth: string;
  ssn_masked?: string | null;
  dl_number?: string | null;
  dl_state?: string | null;
  dl_expiry?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  country: string;
  credit_score?: number | null;
  risk_tier?: string | null;
  created_at: string;
}

export interface CustomerListItem {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  city?: string | null;
  state?: string | null;
  risk_tier?: string | null;
  created_at: string;
}

export type PolicyType = "auto" | "home" | "life";

export type QuoteStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "rejected"
  | "bound"
  | "expired";

export type PolicyStatus =
  | "draft"
  | "under_review"
  | "active"
  | "lapsed"
  | "cancelled"
  | "expired";

export type PaymentFrequency =
  | "monthly"
  | "quarterly"
  | "semi_annual"
  | "annual";

export type EndorsementType =
  | "add_vehicle"
  | "remove_vehicle"
  | "coverage_change"
  | "address_change"
  | "beneficiary_change"
  | "deductible_change"
  | "limits_change"
  | "other";

export type EndorsementStatus = "pending" | "approved" | "rejected";

export interface RatingFactor {
  name: string;
  multiplier: number;
}

export interface QuoteListItem {
  id: string;
  customer_id: string;
  policy_type: PolicyType;
  status: QuoteStatus;
  quoted_premium?: string | null;
  risk_tier?: string | null;
  effective_date?: string | null;
  expiry_date?: string | null;
  created_at: string;
}

export interface Quote {
  id: string;
  customer_id: string;
  policy_type: PolicyType;
  status: QuoteStatus;
  quoted_premium?: string | null;
  monthly_premium?: string | null;
  risk_tier?: string | null;
  rating_inputs?: Record<string, unknown> | null;
  rating_factors?: RatingFactor[] | null;
  policy_details?: Record<string, unknown> | null;
  decline_reasons?: string[] | null;
  effective_date?: string | null;
  expiry_date?: string | null;
  agent_id?: string | null;
  underwriter_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export type PaymentType = "premium" | "claim_payout" | "refund" | "fee";

export type PaymentMethod = "ach" | "credit_card" | "check" | "wire" | "cash";

export type PaymentStatus =
  | "pending"
  | "completed"
  | "failed"
  | "voided"
  | "refunded";

export interface Payment {
  id: string;
  schedule_id?: string | null;
  claim_id?: string | null;
  customer_id: string;
  payment_type: PaymentType;
  amount: string;
  currency: string;
  method?: PaymentMethod | null;
  status: PaymentStatus;
  reference_number?: string | null;
  processed_at?: string | null;
  notes?: string | null;
  created_at: string;
  policy_number?: string | null;
  claim_number?: string | null;
  customer_name?: string | null;
}

export interface PremiumSchedule {
  id: string;
  policy_id: string;
  due_date: string;
  amount_due: string;
  amount_paid: string;
  balance: string;
  status: string;
  created_at: string;
}

export interface Beneficiary {
  id: string;
  full_name: string;
  relationship_type?: string | null;
  allocation_pct: string;
  ssn_last4?: string | null;
  date_of_birth?: string | null;
  is_contingent: boolean;
}

export interface PolicyListItem {
  id: string;
  policy_number: string;
  customer_id: string;
  policy_type: PolicyType;
  status: PolicyStatus;
  effective_date: string;
  expiration_date: string;
  annual_premium: string;
  payment_frequency: PaymentFrequency;
  created_at: string;
}

export interface Policy {
  id: string;
  policy_number: string;
  customer_id: string;
  quote_id?: string | null;
  policy_type: PolicyType;
  status: PolicyStatus;
  effective_date: string;
  expiration_date: string;
  annual_premium: string;
  payment_frequency: PaymentFrequency;
  agent_id?: string | null;
  underwriter_id?: string | null;
  cancellation_reason?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at: string;
  auto_details?: Record<string, unknown> | null;
  home_details?: Record<string, unknown> | null;
  life_details?: Record<string, unknown> | null;
  beneficiaries: Beneficiary[];
  premium_schedules: PremiumSchedule[];
}

export interface Endorsement {
  id: string;
  policy_id: string;
  endorsement_number?: string | null;
  type: EndorsementType;
  effective_date: string;
  description?: string | null;
  premium_impact?: string | null;
  status: EndorsementStatus;
  requested_by?: string | null;
  approved_by?: string | null;
  created_at: string;
  updated_at: string;
}

export type DocumentOwnerType = "policy" | "claim" | "customer" | "quote";

export type DocumentType =
  | "policy_pdf"
  | "claim_decision_letter"
  | "id_document"
  | "vehicle_photo"
  | "property_photo"
  | "police_report"
  | "medical_report"
  | "repair_estimate"
  | "proof_of_ownership"
  | "receipt"
  | "other";

export interface DocumentRecord {
  id: string;
  owner_type: DocumentOwnerType;
  owner_id: string;
  document_type: DocumentType;
  file_name: string;
  mime_type?: string | null;
  storage_bucket: string;
  file_size_bytes?: number | null;
  checksum_sha256?: string | null;
  uploaded_by?: string | null;
  is_verified: boolean;
  verified_by?: string | null;
  created_at: string;
}

export interface DocumentPresign {
  upload_url: string;
  storage_bucket: string;
  storage_key: string;
  expires_in_seconds: number;
}

export interface DocumentDownload {
  download_url: string;
  file_name: string;
  expires_in_seconds: number;
}

export type NotificationType =
  | "claim_submitted"
  | "claim_status_changed"
  | "claim_approved"
  | "claim_rejected"
  | "policy_expiring"
  | "policy_lapsed"
  | "payment_due"
  | "payment_overdue"
  | "payment_received"
  | "quote_ready"
  | "endorsement_approved"
  | "general";

export interface AppNotification {
  id: string;
  type: NotificationType;
  title?: string | null;
  body?: string | null;
  is_read: boolean;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
  sent_via_email: boolean;
  created_at: string;
}

export function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function formatMoney(value?: string | number | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export type ClaimType =
  | "auto_collision"
  | "auto_comprehensive"
  | "auto_liability"
  | "home_dwelling"
  | "home_personal_property"
  | "home_liability"
  | "life_death_benefit";

export type ClaimStatus =
  | "submitted"
  | "assigned"
  | "investigating"
  | "info_requested"
  | "approved"
  | "rejected"
  | "disputed"
  | "paid"
  | "closed";

export interface ClaimNote {
  id: string;
  claim_id: string;
  author_id?: string | null;
  note_type: string;
  body: string;
  is_visible_to_customer: boolean;
  created_at: string;
}

export interface ClaimListItem {
  id: string;
  claim_number: string;
  policy_id: string;
  customer_id: string;
  claim_type: ClaimType;
  status: ClaimStatus;
  incident_date: string;
  estimated_damage?: string | null;
  approved_amount?: string | null;
  fraud_flag: boolean;
  adjuster_id?: string | null;
  created_at: string;
}

export interface Claim {
  id: string;
  claim_number: string;
  policy_id: string;
  customer_id: string;
  claim_type: ClaimType;
  incident_date: string;
  reported_date: string;
  description: string;
  incident_location?: string | null;
  estimated_damage?: string | null;
  approved_amount?: string | null;
  final_payout?: string | null;
  status: ClaimStatus;
  fraud_flag: boolean;
  fraud_score?: string | null;
  adjuster_id?: string | null;
  created_at: string;
  updated_at: string;
  notes: ClaimNote[];
}

export interface AuditLog {
  id: string;
  actor_id?: string | null;
  actor_role?: UserRole | null;
  actor_email?: string | null;
  actor_name?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  old_value?: Record<string, unknown> | null;
  new_value?: Record<string, unknown> | null;
  ip_address?: string | null;
  user_agent?: string | null;
  request_id?: string | null;
  created_at: string;
}

export interface NamedCount {
  key: string;
  label: string;
  count: number;
}

export interface MonthCount {
  month: string;
  count: number;
}

export interface AgentProductionRow {
  agent_id: string;
  agent_name: string;
  policies_written: number;
  annual_premium: string;
}

export interface ManagerDashboard {
  active_policies_total: number;
  active_policies_by_type: NamedCount[];
  new_policies_this_month: number;
  new_policies_last_month: number;
  new_policies_sparkline: MonthCount[];
  open_claims: number;
  avg_days_to_close: number | null;
  loss_ratio_12m: string | null;
  premium_collected_mtd: string;
  premium_target_mtd: string;
  top_agents: AgentProductionRow[];
  claims_by_status: NamedCount[];
  payments_overdue: number;
}

export interface AgentActivityItem {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
  summary?: string | null;
}

export interface AgentDashboard {
  customers_total: number;
  customers_new_this_month: number;
  policies_active: number;
  policies_expiring_30d: number;
  pending_quote_approvals: number;
  recent_activity: AgentActivityItem[];
}

export interface AdjusterQueueItem {
  id: string;
  claim_number: string;
  status: ClaimStatus;
  fraud_flag: boolean;
  estimated_damage?: string | null;
  created_at: string;
  age_days: number;
  days_info_remaining?: number | null;
}

export interface AdjusterDashboard {
  assigned_queue: AdjusterQueueItem[];
  awaiting_info: AdjusterQueueItem[];
  avg_days_to_resolution_personal: number | null;
  avg_days_to_resolution_team: number | null;
  claims_closed_this_month: number;
}

export interface CustomerPolicyCard {
  id: string;
  policy_number: string;
  policy_type: PolicyType;
  status: string;
  next_payment_date?: string | null;
  next_payment_amount?: string | null;
}

export interface CustomerClaimCard {
  id: string;
  claim_number: string;
  status: ClaimStatus;
  incident_date: string;
  estimated_damage?: string | null;
}

export interface CustomerPaymentCard {
  id: string;
  amount: string;
  status: string;
  payment_type: string;
  processed_at?: string | null;
  reference_number?: string | null;
}

export interface CustomerDashboard {
  active_policies: CustomerPolicyCard[];
  open_claims: CustomerClaimCard[];
  recent_payments: CustomerPaymentCard[];
  unread_notifications: number;
}

export interface LossRatioRow {
  policy_type: PolicyType;
  premium_collected: string;
  claims_paid: string;
  loss_ratio: string | null;
}

export interface DemoPersona {
  role: UserRole;
  label: string;
  email: string;
  password: string;
  description: string;
}

export interface PublicConfig {
  app_name: string;
  demo_mode_enabled: boolean;
  chat_widget_enabled: boolean;
  github_repo_url?: string | null;
  api_docs_path: string;
  personas: DemoPersona[];
}

export type ChatSessionMode = "ai" | "human";
export type ChatMessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  body: string;
  sender_kind?: string | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  mode: ChatSessionMode;
  agent_name?: string | null;
  context?: string | null;
  user_id?: string | null;
  created_at: string;
  messages: ChatMessage[];
}

export interface ChatMessageReply {
  session: ChatSession;
  user_message: ChatMessage;
  reply: ChatMessage;
}
