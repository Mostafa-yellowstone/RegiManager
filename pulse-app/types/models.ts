/** Domain + view models for RegiManager Pulse (owner tracking). */

export type DateRangePreset =
  | 'today'
  | 'yesterday'
  | 'week'
  | 'month'
  | 'ytd'
  | 'custom';

/** `all` | virtual `dmv` | real Space id */
export type SpaceIdOrAll = string | 'all' | 'dmv';

export type TargetPeriod = 'daily' | 'weekly' | 'monthly';

export type TargetType = 'revenue' | 'service_count';

export interface ComparativeBadge {
  label: string;
  delta_pct: number;
}

export interface FinancialOverview {
  space_id: SpaceIdOrAll;
  range: DateRangePreset;
  /** Ops net profit (DMV processing net + space profits; insurance = commission + broker). */
  net_profit: number;
  /** Real banking expenses (not DMV fee/tax/card lines). */
  bank_expenses: number;
  /** Banking income in range. */
  bank_income: number;
  /** Banking net cash flow (credit transfers − debit transfers). */
  net_cash_flow: number;
  /** Banking income − expenses. */
  bank_net: number;
  /** DMV = processing fee (matches CRM). */
  dmv_net_profit: number;
  /** Insurance commission only. */
  insurance_commission: number;
  /** Insurance broker fees only. */
  insurance_broker_fee: number;
  /** commission + broker_fee */
  insurance_profit: number;
  records_count: number;
  insurance_bound_count: number;
  badges: {
    profit?: ComparativeBadge;
    expenses?: ComparativeBadge;
    dmv?: ComparativeBadge;
    insurance?: ComparativeBadge;
  };
  series: Array<{ timestamp: number; value: number }>;
  /** False when cashflow API failed (e.g. banking permission). */
  cashflow_available: boolean;
  cashflow_warning?: string;
}

export interface ServiceBreakdownRow {
  service_id: string;
  name: string;
  category: string;
  bookings: number;
  revenue: number;
  avg_ticket: number;
  peak_hour_label: string;
  meta?: string;
}

export interface TargetProgressRow {
  period: TargetPeriod;
  type: TargetType;
  target_amount: number;
  actual_amount: number;
  progress_pct: number;
  run_rate_amount: number;
  run_rate_label: string;
}

export interface SpaceSummary {
  space_id: string;
  name: string;
  location: string;
  key?: string;
  /** Space profit for selected range (Insurance = commission + broker). */
  profit: number;
  revenue: number;
}

export interface CostFeeRow {
  id: string;
  label: string;
  category: string;
  amount: number;
  date?: string;
  account?: string;
  company?: string;
  transaction_type?: string;
}

export interface ActivityRow {
  id: string;
  title: string;
  subtitle: string;
  amount: number;
  date: string;
  category: string;
}

export interface AgentRosterRow {
  membership_id: number;
  name: string;
  role: string;
  attendance_open: boolean;
  attendance_label: string;
  started_at: string;
  ended_at: string;
  is_late: boolean;
  task_percent: number;
  service_revenue_total: number;
  service_records_total: number;
}

export interface PulseDashboardPayload {
  overview: FinancialOverview;
  services: ServiceBreakdownRow[];
  targets: TargetProgressRow[];
  space_summaries: SpaceSummary[];
  costs: CostFeeRow[];
  organization_name?: string;
}
