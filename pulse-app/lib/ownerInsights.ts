import type {
  AgentRosterRow,
  ComparativeBadge,
  FinancialOverview,
  SpaceSummary,
} from '@/types/models';

export type AttentionLevel = 'critical' | 'warning' | 'info';

export type AttentionItem = {
  id: string;
  level: AttentionLevel;
  title: string;
  body: string;
  href: '/(tabs)/staff' | '/(tabs)/expenses' | '/(tabs)/sales' | '/(tabs)/insurance' | '/(tabs)';
};

export type MorningBriefModel = {
  /** DMV processing profit + insurance broker fee (when insurance exists). */
  netProfit: number;
  profitHint: string;
  cashFlow: number;
  bankExpenses: number;
  onDuty: number;
  late: number;
  onTime: number;
  workDate?: string;
  profitBadge?: ComparativeBadge;
  expenseBadge?: ComparativeBadge;
  asOfLabel: string;
  hasInsurance: boolean;
};

export function orgHasInsuranceSpace(spaceSummaries?: SpaceSummary[] | null): boolean {
  return (spaceSummaries ?? []).some((s) => (s.key || '').toLowerCase() === 'insurance');
}

/**
 * Morning Brief profit = DMV net + insurance broker fee only (when the PSB has Insurance).
 * Does not include insurance commission.
 */
export function buildMorningBrief(params: {
  overview?: FinancialOverview | null;
  agents?: AgentRosterRow[];
  workDate?: string;
  asOfLabel?: string;
  hasInsurance?: boolean;
  spaceSummaries?: SpaceSummary[] | null;
}): MorningBriefModel | null {
  const overview = params.overview;
  if (!overview) return null;
  const agents = params.agents ?? [];
  const hasInsurance =
    params.hasInsurance ?? orgHasInsuranceSpace(params.spaceSummaries);

  const dmv = overview.dmv_net_profit || 0;
  const broker = hasInsurance ? overview.insurance_broker_fee || 0 : 0;

  return {
    netProfit: dmv + broker,
    profitHint: hasInsurance ? 'DMV + broker fee' : 'DMV processing',
    cashFlow: overview.net_cash_flow || 0,
    bankExpenses: overview.bank_expenses || 0,
    onDuty: agents.filter((a) => a.attendance_open).length,
    late: agents.filter((a) => a.is_late).length,
    onTime: agents.filter((a) => a.is_on_time).length,
    workDate: params.workDate,
    profitBadge: overview.badges.profit,
    expenseBadge: overview.badges.expenses,
    asOfLabel: params.asOfLabel || 'Selected range',
    hasInsurance,
  };
}

export function buildAttentionItems(params: {
  overview?: FinancialOverview | null;
  agents?: AgentRosterRow[];
  salesCount?: number | null;
  spaceSummaries?: SpaceSummary[];
}): AttentionItem[] {
  const items: AttentionItem[] = [];
  const agents = params.agents ?? [];
  const lateAgents = agents.filter((a) => a.is_late);
  const overview = params.overview;
  const hasInsurance = orgHasInsuranceSpace(params.spaceSummaries);

  if (lateAgents.length > 0) {
    const names = lateAgents
      .slice(0, 2)
      .map((a) => a.name.split(/\s+/)[0] || a.name)
      .join(', ');
    const more = lateAgents.length > 2 ? ` +${lateAgents.length - 2}` : '';
    items.push({
      id: 'late-staff',
      level: 'critical',
      title: `${lateAgents.length} staff late`,
      body: `${names}${more}. Egypt start is 4:00 PM Cairo.`,
      href: '/(tabs)/staff',
    });
  }

  const expenseDelta = overview?.badges.expenses?.delta_pct;
  if (typeof expenseDelta === 'number' && expenseDelta >= 25) {
    items.push({
      id: 'expense-spike',
      level: 'warning',
      title: 'Expenses spiked',
      body: `Bank expenses are ${expenseDelta > 0 ? '+' : ''}${expenseDelta.toFixed(0)}% vs prior period.`,
      href: '/(tabs)/expenses',
    });
  }

  const profitDelta = overview?.badges.profit?.delta_pct;
  if (typeof profitDelta === 'number' && profitDelta <= -15) {
    items.push({
      id: 'profit-down',
      level: 'warning',
      title: 'Profit soft vs prior',
      body: `Net profit is ${profitDelta.toFixed(0)}% vs the previous period.`,
      href: '/(tabs)',
    });
  }

  if (overview && !overview.cashflow_available) {
    items.push({
      id: 'cashflow-unavailable',
      level: 'info',
      title: 'Bank cash flow limited',
      body: overview.cashflow_warning || 'Banking metrics may be incomplete for this account.',
      href: '/(tabs)/expenses',
    });
  }

  if (params.salesCount === 0) {
    items.push({
      id: 'quiet-sales',
      level: 'info',
      title: 'No sales in this range',
      body: 'DMV/insurance payments are empty for the selected dates.',
      href: '/(tabs)/sales',
    });
  }

  if (hasInsurance && overview && (overview.insurance_bound_count || 0) === 0) {
    items.push({
      id: 'quiet-insurance',
      level: 'info',
      title: 'No insurance binds',
      body: 'Open the Insurance tab to review premiums and commission by carrier.',
      href: '/(tabs)/insurance',
    });
  }

  const spaces = params.spaceSummaries ?? [];
  const softSpace = spaces
    .filter((s) => typeof s.profit === 'number')
    .slice()
    .sort((a, b) => a.profit - b.profit)[0];
  if (softSpace && softSpace.profit < 0) {
    items.push({
      id: `space-soft-${softSpace.space_id}`,
      level: 'warning',
      title: `${softSpace.name} is negative`,
      body: 'This space lost money in the selected range. Tap Spaces on Pulse to filter.',
      href: '/(tabs)',
    });
  }

  return items.slice(0, 5);
}

export function spaceInsight(space: SpaceSummary): string {
  if (space.profit > 0) return 'Contributing to profit';
  if (space.profit < 0) return 'Needs attention';
  return 'Flat in this range';
}
