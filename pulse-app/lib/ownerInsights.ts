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
      title: `${lateAgents.length} late`,
      body: `${names}${more}`,
      href: '/(tabs)/staff',
    });
  }

  const expenseDelta = overview?.badges.expenses?.delta_pct;
  if (typeof expenseDelta === 'number' && expenseDelta >= 25) {
    items.push({
      id: 'expense-spike',
      level: 'warning',
      title: 'Money out jumped',
      body: `${expenseDelta > 0 ? '+' : ''}${expenseDelta.toFixed(0)}% versus the previous period.`,
      href: '/(tabs)/expenses',
    });
  }

  const profitDelta = overview?.badges.profit?.delta_pct;
  if (typeof profitDelta === 'number' && profitDelta <= -15) {
    items.push({
      id: 'profit-down',
      level: 'warning',
      title: 'Quieter than last period',
      body: `${profitDelta.toFixed(0)}% versus the previous period.`,
      href: '/(tabs)',
    });
  }

  if (overview && !overview.cashflow_available) {
    items.push({
      id: 'cashflow-unavailable',
      level: 'info',
      title: 'Bank lines are incomplete',
      body: overview.cashflow_warning || 'Some bank lines are missing for this account.',
      href: '/(tabs)/expenses',
    });
  }

  if (params.salesCount === 0) {
    items.push({
      id: 'quiet-sales',
      level: 'info',
      title: 'No payments in this range',
      body: 'The desk and insurance lists are empty for these dates.',
      href: '/(tabs)/sales',
    });
  }

  if (hasInsurance && overview && (overview.insurance_bound_count || 0) === 0) {
    items.push({
      id: 'quiet-insurance',
      level: 'info',
      title: 'No insurance binds',
      body: 'Nothing was bound in this range.',
      href: '/(tabs)/sales',
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
      title: `${softSpace.name} is down`,
      body: 'This part of the office is down for the selected range.',
      href: '/(tabs)',
    });
  }

  return items.slice(0, 3);
}

export function spaceInsight(space: SpaceSummary): string {
  if (space.profit > 0) return 'Contributing to profit';
  if (space.profit < 0) return 'Needs attention';
  return 'Flat in this range';
}
