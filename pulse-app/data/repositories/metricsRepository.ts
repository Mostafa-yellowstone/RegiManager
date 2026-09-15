import {
  ApiError,
  fetchOwnerFinanceCashflow,
  fetchOwnerFinanceChart,
  fetchOwnerFinanceCompare,
  fetchOwnerFinanceSummary,
  fetchOwnerOverview,
  fetchOwnerProcesses,
  fetchOwnerSpaceDetail,
  fetchOwnerSpaces,
} from '@/lib/api';
import {
  currentMonthKey,
  presetToDateParams,
  previousMonthKey,
  previousPeriodDateParams,
} from '@/lib/dateRange';
import { adaptPulseDashboard } from '@/data/adapters/pulseAdapter';
import type { DateRangePreset, PulseDashboardPayload, SpaceIdOrAll } from '@/types/models';

function isVirtualSpace(spaceId: SpaceIdOrAll) {
  return spaceId === 'all' || spaceId === 'dmv';
}

export async function getPulseDashboard(
  spaceId: SpaceIdOrAll,
  preset: DateRangePreset,
): Promise<PulseDashboardPayload> {
  const { from_date, to_date } = presetToDateParams(preset);
  const rangeParams = { from_date, to_date };
  const priorParams = previousPeriodDateParams(preset);

  const comparePromise =
    preset === 'month' || preset === 'ytd'
      ? fetchOwnerFinanceCompare(previousMonthKey(), currentMonthKey()).catch(() => null)
      : Promise.resolve(null);

  const cashflowResult = await fetchOwnerFinanceCashflow(rangeParams)
    .then((data) => ({ data, error: null as string | null }))
    .catch((err: unknown) => {
      const status = err instanceof ApiError ? err.status : 0;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Cashflow request failed';
      // 404 = endpoint not deployed yet; finance.summary.banking is the fallback.
      if (status === 404) {
        return { data: null, error: null };
      }
      return { data: null, error: message };
    });

  const [
    overview,
    finance,
    chart,
    spaces,
    processes,
    compare,
    spaceDetail,
    priorCashflow,
    priorOverview,
    priorFinance,
  ] = await Promise.all([
    fetchOwnerOverview(rangeParams),
    fetchOwnerFinanceSummary(rangeParams),
    fetchOwnerFinanceChart(12),
    fetchOwnerSpaces(rangeParams),
    fetchOwnerProcesses().catch(() => null),
    comparePromise,
    !isVirtualSpace(spaceId)
      ? fetchOwnerSpaceDetail(spaceId, rangeParams).catch(() => null)
      : Promise.resolve(null),
    fetchOwnerFinanceCashflow(priorParams).catch(() => null),
    fetchOwnerOverview(priorParams).catch(() => null),
    fetchOwnerFinanceSummary(priorParams).catch(() => null),
  ]);

  const resolvedPriorCashflow =
    priorCashflow?.cashflow ? priorCashflow : priorFinance?.banking?.cashflow ? priorFinance.banking : null;

  return adaptPulseDashboard({
    overview,
    finance,
    chart,
    spaces,
    cashflow: cashflowResult.data,
    cashflowError: cashflowResult.error,
    processes,
    compare,
    priorCashflow: resolvedPriorCashflow,
    priorOverview,
    spaceDetail,
    spaceId,
    preset,
  });
}
