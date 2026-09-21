import { formatMoney } from '@/lib/format';
import type { InsuranceSummaryPayload } from '@/types/models';

export type InsuranceRecommendation = {
  id: string;
  level: 'critical' | 'warning' | 'info';
  title: string;
  body: string;
};

/** Owner-facing coaching tips from insurance book + period metrics. */
export function buildInsuranceRecommendations(
  summary: InsuranceSummaryPayload | null | undefined,
): InsuranceRecommendation[] {
  if (!summary?.available) return [];

  const items: InsuranceRecommendation[] = [];
  const t = summary.totals;
  const companies = summary.companies;

  if (t.unearned_commission > 0) {
    items.push({
      id: 'chase-unearned',
      level: t.unearned_commission >= 1000 ? 'critical' : 'warning',
      title: 'Unearned commission sitting',
      body: `${formatMoney(t.unearned_commission)} is still unearned on the book. Review cancelled/inactive policies and chase remittance in CRM.`,
    });
  }

  if (t.earned_commission > 0 && t.received_commission / Math.max(t.earned_commission, 1) < 0.7) {
    const gap = Math.max(t.earned_commission - t.received_commission, 0);
    items.push({
      id: 'collect-earned',
      level: 'warning',
      title: 'Earned commission not fully received',
      body: `${formatMoney(gap)} earned is still outstanding. Mark remittances received when carrier deposits land.`,
    });
  }

  if (t.period_bound_count === 0) {
    items.push({
      id: 'quiet-binds',
      level: 'info',
      title: 'No binds in this range',
      body: 'Pipeline may be stuck in quotes. Check open quotes and producer follow-ups in CRM Insurance.',
    });
  } else if (t.period_premium > 0 && t.period_broker_fee / t.period_premium < 0.02) {
    items.push({
      id: 'broker-mix',
      level: 'info',
      title: 'Broker fee share is light',
      body: `Broker fees are ${formatMoney(t.period_broker_fee)} on ${formatMoney(t.period_premium)} premium. Confirm fee schedules are applied on binds.`,
    });
  }

  if (companies.length > 0) {
    const top = [...companies].sort((a, b) => b.period_premium - a.period_premium)[0];
    const share =
      t.period_premium > 0 ? (top.period_premium / t.period_premium) * 100 : 0;
    if (share >= 60 && top.period_premium > 0) {
      items.push({
        id: 'carrier-concentration',
        level: 'warning',
        title: `${top.name} dominates premium`,
        body: `${share.toFixed(0)}% of period premium is with one carrier. Spread appetite or watch appointment risk.`,
      });
    }

    const highUnearned = [...companies]
      .filter((c) => c.unearned_commission > 0)
      .sort((a, b) => b.unearned_commission - a.unearned_commission)[0];
    if (highUnearned && highUnearned.unearned_commission >= 250) {
      items.push({
        id: `carrier-unearned-${highUnearned.id}`,
        level: 'info',
        title: `Focus ${highUnearned.name}`,
        body: `${formatMoney(highUnearned.unearned_commission)} unearned at this carrier. Start remittance cleanup there.`,
      });
    }
  }

  if (t.active_policy_count > 0 && t.book_premium === 0) {
    items.push({
      id: 'premium-missing',
      level: 'warning',
      title: 'Active policies missing premium',
      body: 'Book shows active policies but $0 premium. Audit policy premium fields in CRM.',
    });
  }

  if (items.length === 0) {
    items.push({
      id: 'healthy-book',
      level: 'info',
      title: 'Insurance book looks steady',
      body: 'Commissions and premium are in a healthy range for this snapshot. Keep weekly remittance reviews.',
    });
  }

  return items.slice(0, 4);
}
