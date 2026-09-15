/** Domain models for RegiManager Pulse (UUID-ready string IDs). */

export type UserRole = 'owner' | 'manager' | 'employee';

export type AttendanceStatus =
  | 'on_duty'
  | 'on_break'
  | 'late'
  | 'absent'
  | 'scheduled';

export type ExpenseCategoryKind = 'fixed' | 'variable';

export type TargetType = 'revenue' | 'service_count';

export type TargetPeriod = 'daily' | 'weekly' | 'monthly';

export type DateRangePreset =
  | 'today'
  | 'yesterday'
  | 'week'
  | 'month'
  | 'ytd'
  | 'custom';

export type SpaceIdOrAll = string | 'all';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar_url?: string | null;
  space_ids: string[];
}

export interface Space {
  id: string;
  name: string;
  location: string;
  timezone: string;
  operational_hours: {
    open: string;
    close: string;
  };
}

export interface Service {
  id: string;
  space_id: string;
  name: string;
  cost: number;
  price: number;
  category: string;
  duration_minutes: number;
}

export interface Sale {
  id: string;
  space_id: string;
  service_id: string;
  staff_id: string;
  amount: number;
  tax: number;
  discount: number;
  date: string; // ISO
}

export interface Expense {
  id: string;
  space_id: string;
  category: string;
  kind: ExpenseCategoryKind;
  amount: number;
  receipt_url?: string | null;
  date: string;
  notes?: string;
}

export interface Attendance {
  id: string;
  staff_id: string;
  space_id: string;
  clock_in: string;
  clock_out?: string | null;
  status: AttendanceStatus;
  break_minutes: number;
}

export interface Target {
  id: string;
  space_id: string;
  type: TargetType;
  target_amount: number;
  period: TargetPeriod;
  start_date: string;
  end_date: string;
}

/** Aggregated dashboard DTOs */

export interface ComparativeBadge {
  label: string;
  delta_pct: number;
}

export interface FinancialOverview {
  space_id: SpaceIdOrAll;
  range: DateRangePreset;
  gross_revenue: number;
  total_expenses: number;
  net_profit: number;
  profit_margin_pct: number;
  badges: {
    revenue: ComparativeBadge;
    expenses: ComparativeBadge;
    profit: ComparativeBadge;
    margin: ComparativeBadge;
  };
  series: Array<{ timestamp: number; value: number }>;
}

export interface ServiceBreakdownRow {
  service_id: string;
  name: string;
  category: string;
  bookings: number;
  revenue: number;
  avg_ticket: number;
  peak_hour_label: string;
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

export interface PulseDashboardPayload {
  overview: FinancialOverview;
  services: ServiceBreakdownRow[];
  targets: TargetProgressRow[];
  space_summaries: Array<{
    space_id: string;
    name: string;
    location: string;
    revenue: number;
  }>;
}
