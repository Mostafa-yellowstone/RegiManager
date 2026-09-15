import type {
  CostFeeRow,
  DateRangePreset,
  FinancialOverview,
  PulseDashboardPayload,
  ServiceBreakdownRow,
  SpaceIdOrAll,
  SpaceSummary,
  TargetProgressRow,
} from '@/types/models';
import { compareBadgeLabel } from '@/lib/dateRange';

function money(value: unknown): number {
  if (value == null) return 0;
  const n = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  return Number.isFinite(n) ? n : 0;
}

function pctDelta(current: number, previous: number): number {
  if (previous === 0) return current === 0 ? 0 : 100;
  return Number((((current - previous) / Math.abs(previous)) * 100).toFixed(1));
}

/** When API was called with from/to, prefer the `custom` bucket. */
function hasCustomRange(payload: any): boolean {
  return Boolean(payload?.range?.from && payload?.range?.to);
}

function activePeriod(report: any, useCustom: boolean) {
  if (!report) return {};
  if (useCustom && report.custom) return report.custom;
  return report.month || report.today || report.year || {};
}

export function adaptChart(chart: any): Array<{ timestamp: number; value: number }> {
  const labels: string[] = chart?.labels || [];
  // DMV processing profit trend (not gross service_fee revenue).
  const series: string[] = chart?.gross_profit || chart?.revenue || [];
  return labels.map((label, i) => {
    const parsed = Date.parse(`1 ${label}`);
    return {
      timestamp: Number.isFinite(parsed) ? parsed : Date.now() - (labels.length - i) * 86400000 * 30,
      value: money(series[i]),
    };
  });
}

export function adaptSpacesList(spacesPayload: any, useCustom: boolean): SpaceSummary[] {
  const rows: any[] = spacesPayload?.spaces || spacesPayload?.results || [];
  return rows.map((space) => {
    const period = useCustom && space.custom ? space.custom : space.month || space.today || {};
    return {
      space_id: String(space.id),
      name: space.name || space.label || 'Space',
      location: space.description || space.key || '',
      key: space.key,
      profit: money(period.profit),
      revenue: money(period.revenue),
    };
  });
}

function buildTargets(goal: any): TargetProgressRow[] {
  if (!goal) return [];
  const target = money(goal.suggested_goal);
  const actual = money(goal.mtd_revenue);
  const projected = money(goal.projected_month_end);
  const pace = money(goal.pace_pct);
  const mtdPct = money(goal.mtd_pct);
  return [
    {
      period: 'monthly',
      type: 'revenue',
      target_amount: target || money(goal.prev_month_revenue) || 1,
      actual_amount: actual,
      progress_pct: Math.min(100, Math.round(mtdPct || (target ? (actual / target) * 100 : 0))),
      run_rate_amount: projected,
      run_rate_label: goal.status_label || 'Projected month-end',
    },
    {
      period: 'daily',
      type: 'revenue',
      target_amount: money(goal.required_daily_pace) || money(goal.daily_run_rate) || 1,
      actual_amount: money(goal.daily_run_rate),
      progress_pct: Math.min(100, Math.round(pace || 0)),
      run_rate_amount: money(goal.daily_run_rate),
      run_rate_label: 'Daily run rate',
    },
  ];
}

function buildBankExpenses(cashflow: any): CostFeeRow[] {
  const rows: any[] = cashflow?.expenses || [];
  return rows.map((tx) => ({
    id: String(tx.id),
    label: tx.description || tx.category || 'Expense',
    category: tx.category || 'Banking',
    amount: money(tx.amount),
    date: tx.date || '',
    account: tx.account || '',
    company: tx.company || '',
    transaction_type: tx.transaction_type_label || tx.transaction_type || '',
  }));
}

function buildActivityFromProcesses(processes: any): ServiceBreakdownRow[] {
  const recent = processes?.recent_services || [];
  return recent.map((row: any) => ({
    service_id: String(row.id),
    name: row.service_type || 'Service',
    category: row.status || 'DMV',
    bookings: 1,
    revenue: money(row.processing_fee),
    avg_ticket: money(row.processing_fee),
    peak_hour_label: row.transaction_date || '',
    meta: [row.client_name, row.handled_by].filter(Boolean).join(' · '),
  }));
}

function insuranceProfitFromOverview(overview: any): number {
  const useCustom = hasCustomRange(overview) || true;
  const profit = overview?.profit || {};
  const insurance = profit.insurance || {};
  const insActive = activePeriod(insurance, useCustom);
  const commission = money(insActive.commission);
  const broker = money(insActive.broker_fee);
  return money(insActive.total_profit) || commission + broker;
}

export function adaptPulseDashboard(input: {
  overview: any;
  finance: any;
  chart: any;
  spaces: any;
  cashflow?: any | null;
  cashflowError?: string | null;
  processes?: any;
  compare?: any;
  priorCashflow?: any | null;
  priorOverview?: any | null;
  spaceDetail?: any;
  spaceId: SpaceIdOrAll;
  preset: DateRangePreset;
}): PulseDashboardPayload {
  const useCustom =
    hasCustomRange(input.overview) ||
    hasCustomRange(input.finance) ||
    hasCustomRange(input.cashflow) ||
    true;

  // Prefer dedicated cashflow endpoint; fall back to finance.summary banking embed
  // (works when /finance/cashflow/ is not deployed yet → 404).
  const resolvedCashflow = input.cashflow?.cashflow
    ? input.cashflow
    : input.finance?.banking?.cashflow
      ? input.finance.banking
      : null;

  const profit = input.overview?.profit || {};
  const dmv = profit.dmv_core || input.finance?.dmv || {};
  const insurance = profit.insurance || input.finance?.insurance || {};
  const dmvActive = activePeriod(dmv, useCustom);
  const insActive = activePeriod(insurance, useCustom);

  // CRM DMV profit = processing fee (gross_profit).
  const dmvProfit = money(dmvActive.gross_profit ?? dmvActive.net_profit_after_referral);
  const insuranceCommission = money(insActive.commission);
  const insuranceBroker = money(insActive.broker_fee);
  const insuranceProfit = money(insActive.total_profit) || insuranceCommission + insuranceBroker;
  const insuranceBound = Number(insActive.bound_count || 0);

  let recordsCount = Number(dmvActive.total_records || 0);
  let boundCount = insuranceBound;
  let spaceInsuranceCommission = insuranceCommission;
  let spaceInsuranceBroker = insuranceBroker;
  let spaceInsuranceProfit = insuranceProfit;
  let showDmv = true;
  let showInsurance = true;

  const isDmvVirtual = input.spaceId === 'dmv';
  const isAll = input.spaceId === 'all';
  const isInsuranceSpace = !isAll && input.spaceDetail?.key === 'insurance';

  if (isDmvVirtual) {
    spaceInsuranceCommission = 0;
    spaceInsuranceBroker = 0;
    spaceInsuranceProfit = 0;
    boundCount = 0;
    showInsurance = false;
  } else if (!isAll && input.spaceDetail) {
    const sp =
      useCustom && input.spaceDetail.custom
        ? input.spaceDetail.custom
        : input.spaceDetail.month || input.spaceDetail.today || {};
    recordsCount = Number(sp.transactions || input.spaceDetail.total_records || 0);
    if (isInsuranceSpace) {
      spaceInsuranceCommission = insuranceCommission;
      spaceInsuranceBroker = insuranceBroker;
      spaceInsuranceProfit = money(sp.profit) || insuranceProfit;
      showDmv = false;
    } else {
      spaceInsuranceCommission = 0;
      spaceInsuranceBroker = 0;
      spaceInsuranceProfit = 0;
      showInsurance = false;
      showDmv = false;
    }
  }

  const cashflowAvailable = Boolean(resolvedCashflow?.cashflow);
  const cf = resolvedCashflow?.cashflow || {};
  // Finance pager banking metrics.
  const bankExpenses = money(cf.expense);
  const bankIncome = money(cf.income);
  const bankNet = money(cf.net_profit) || bankIncome - bankExpenses;
  // Cash flow card = bank income − expenses (same as Finance net profit).
  const netCashFlow = bankIncome - bankExpenses;

  // Net profit card = insurance profit (commission + broker) + DMV profit.
  let netProfit = insuranceProfit + dmvProfit;
  if (isDmvVirtual) {
    netProfit = dmvProfit;
  } else if (isInsuranceSpace) {
    netProfit = spaceInsuranceProfit + dmvProfit;
  } else if (!isAll && input.spaceDetail) {
    const sp =
      useCustom && input.spaceDetail.custom
        ? input.spaceDetail.custom
        : input.spaceDetail.month || input.spaceDetail.today || {};
    netProfit = money(sp.profit);
  }

  const badgeLabel = compareBadgeLabel(input.preset);
  const badges: FinancialOverview['badges'] = {};
  const deltas = input.compare?.deltas;

  const priorDmv = input.priorOverview ? profitBucketGross(input.priorOverview) : 0;
  const priorIns = input.priorOverview ? insuranceProfitFromOverview(input.priorOverview) : 0;
  const priorOpsProfit = priorIns + priorDmv;

  if (priorOpsProfit || netProfit) {
    badges.profit = { label: badgeLabel, delta_pct: pctDelta(netProfit, priorOpsProfit) };
  } else if (deltas?.net_profit_pct != null) {
    badges.profit = { label: badgeLabel, delta_pct: Number(deltas.net_profit_pct) };
  }

  if (deltas?.gross_profit_pct != null) {
    badges.dmv = { label: badgeLabel, delta_pct: Number(deltas.gross_profit_pct) };
  } else if (input.priorOverview) {
    badges.dmv = { label: badgeLabel, delta_pct: pctDelta(dmvProfit, priorDmv) };
  }

  if (input.priorCashflow?.cashflow) {
    const priorExpense = money(input.priorCashflow.cashflow.expense);
    const priorIncome = money(input.priorCashflow.cashflow.income);
    badges.expenses = { label: badgeLabel, delta_pct: pctDelta(bankExpenses, priorExpense) };
    // Optional: could badge cash flow vs prior income−expense
    void priorIncome;
  }

  if (input.priorOverview) {
    badges.insurance = {
      label: badgeLabel,
      delta_pct: pctDelta(insuranceProfit, priorIns),
    };
  }

  const overview: FinancialOverview = {
    space_id: input.spaceId,
    range: input.preset,
    net_profit: netProfit,
    bank_expenses: bankExpenses,
    bank_income: bankIncome,
    bank_net: bankNet,
    net_cash_flow: netCashFlow,
    dmv_net_profit: showDmv || isDmvVirtual || isAll ? dmvProfit : 0,
    insurance_commission: showInsurance ? spaceInsuranceCommission : 0,
    insurance_broker_fee: showInsurance ? spaceInsuranceBroker : 0,
    insurance_profit: showInsurance ? spaceInsuranceProfit : 0,
    records_count: showDmv || isDmvVirtual ? recordsCount : Number(dmvActive.total_records || 0),
    insurance_bound_count: showInsurance ? boundCount : 0,
    badges,
    series: adaptChart(input.chart),
    cashflow_available: cashflowAvailable,
    cashflow_warning: cashflowAvailable
      ? undefined
      : input.cashflowError
        ? `Banking expenses unavailable (${input.cashflowError}). Pull to refresh after backend deploy.`
        : 'Banking cashflow unavailable. Confirm banking permission on this account.',
  };

  if (isDmvVirtual) {
    overview.records_count = Number(dmvActive.total_records || 0);
  }

  return {
    overview,
    services: buildActivityFromProcesses(input.processes),
    targets: buildTargets(input.finance?.goal_forecast),
    space_summaries: adaptSpacesList(input.spaces, useCustom),
    costs: buildBankExpenses(resolvedCashflow),
    organization_name: input.overview?.organization?.name,
  };
}

function profitBucketGross(overview: any): number {
  const dmv = overview?.profit?.dmv_core || {};
  const active = activePeriod(dmv, true);
  return money(active.gross_profit ?? active.net_profit_after_referral);
}

function formatSessionTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function adaptAgents(payload: any) {
  const agents = payload?.agents || [];
  return agents.map((a: any) => {
    const att = a.attendance;
    const open = Boolean(att?.is_open);
    const started = formatSessionTime(att?.opened_at);
    const ended = formatSessionTime(att?.closed_at);

    // Prefer explicit server NY flags when present.
    let isLate = att?.is_late === true || att?.attendance_status === 'late';
    let isOnTime = att?.is_on_time === true || att?.attendance_status === 'on_time';

    // Fallback: compare NY wall-clock (after 9:00 = late, at/before = on time).
    if (att && att.is_late == null && att.is_on_time == null && att.opened_at && att.shift_open_at) {
      const openedMs = Date.parse(att.opened_at);
      const shiftMs = Date.parse(att.shift_open_at);
      if (Number.isFinite(openedMs) && Number.isFinite(shiftMs)) {
        isLate = openedMs > shiftMs;
        isOnTime = !isLate;
      }
    }

    // No session → neither late nor on time.
    if (!att?.opened_at) {
      isLate = false;
      isOnTime = false;
    }

    let label = 'No session today';
    if (open && isLate && started) label = `Late (after 9:00 AM NY) · since ${started}`;
    else if (open && isOnTime && started) label = `On time · since ${started}`;
    else if (open && started) label = `On duty · since ${started}`;
    else if (open) label = 'On duty';
    else if (isLate && att?.closed_at && started) {
      label = `Late start (after 9:00 AM NY) · ${started} – ${ended}`;
    } else if (isOnTime && att?.closed_at && started) {
      label = `On time · ${started} – ${ended}`;
    } else if (att?.closed_at && started) label = `Off duty · ${started} – ${ended}`;
    else if (att?.closed_at) label = `Off duty · ended ${ended}`;

    return {
      membership_id: a.membership_id ?? a.id,
      name: a.full_name || a.name || a.username || 'Agent',
      role: a.role || 'agent',
      attendance_open: open,
      attendance_label: label,
      started_at: started,
      ended_at: ended,
      is_late: isLate,
      is_on_time: isOnTime,
      task_percent: Number(a.task_progress?.percent ?? 0),
      service_revenue_total: money(a.service_revenue_total),
      service_records_total: Number(a.service_records_total || 0),
    };
  });
}

export function adaptFinanceRecords(payload: any, category: string) {
  const results = payload?.results || [];
  return results.map((row: any) => ({
    id: String(row.id),
    title: row.description || 'Payment',
    subtitle: [row.client_name, row.method, row.reference].filter(Boolean).join(' · '),
    amount: money(row.amount),
    date: row.transaction_date || '',
    category,
  }));
}
