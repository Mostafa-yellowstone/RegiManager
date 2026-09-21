import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useSpaceStore } from '@/stores/spaceStore';

export default function ExpensesScreen() {
  const router = useRouter();
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const spaceId = useSpaceStore((s) => s.selectedSpaceId);
  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-costs', selectedOrg?.id, spaceId, preset, customStart, customEnd],
    queryFn: () => getPulseDashboard(spaceId, preset),
    enabled: Boolean(selectedOrg?.id),
  });

  const costs = data?.costs ?? [];
  const overview = data?.overview;
  const total = overview?.bank_expenses ?? costs.reduce((s, c) => s + c.amount, 0);

  return (
    <ScrollView
      className="flex-1 bg-cream"
      contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
      refreshControl={
        <RefreshControl
          refreshing={isFetching && !isLoading}
          onRefresh={() => {
            void hapticLight();
            void refetch();
          }}
          tintColor="#1A2B48"
        />
      }
    >
      <Text className="text-title text-navy">Expenses</Text>
      <Text className="mb-1 text-caption text-muted">
        Real banking expenses from Insurance Finance. Tap a row for full detail. DMV fees, sales
        tax, card fees, and referral commissions are transaction charges, not listed here.
      </Text>
      <ConnectedDateRangeSelector />

      {isError ? (
        <Text className="text-caption font-semibold text-danger">
          {(error as Error)?.message || 'Failed to load expenses'}
        </Text>
      ) : null}

      {overview && !overview.cashflow_available ? (
        <View className="rounded-xl px-3 py-2" style={{ backgroundColor: Colors.orangeSoft }}>
          <Text className="text-caption font-semibold" style={{ color: Colors.orangeDeep }}>
            {overview.cashflow_warning || 'Banking cashflow unavailable for this account.'}
          </Text>
        </View>
      ) : null}

      {isLoading ? (
        <>
          <SkeletonBlock height={72} />
          <SkeletonBlock height={72} />
        </>
      ) : (
        <>
          <View className="mb-2 rounded-2xl border border-border bg-white p-4">
            <Text className="text-caption uppercase text-muted">Bank expenses in range</Text>
            <Text className="mt-1 text-[28px] font-extrabold text-navy">{formatMoney(total)}</Text>
            {overview ? (
              <Text className="mt-2 text-caption text-muted">
                Net profit {formatMoney(overview.net_cash_flow)} · Bank net{' '}
                {formatMoney(overview.bank_net)}
                {overview.badges.expenses
                  ? ` · ${overview.badges.expenses.delta_pct > 0 ? '+' : ''}${overview.badges.expenses.delta_pct}% ${overview.badges.expenses.label}`
                  : ''}
              </Text>
            ) : null}
          </View>
          {costs.length === 0 ? (
            <Text className="mt-4 text-center text-body text-muted">
              No bank expense transactions in this period.
            </Text>
          ) : (
            costs.map((row) => (
              <Pressable
                key={row.id}
                onPress={() => {
                  void hapticSelection();
                  router.push({
                    pathname: '/expense/[id]',
                    params: {
                      id: row.id,
                      label: row.label,
                      amount: String(row.amount),
                      category: row.category,
                      date: row.date || '',
                      account: row.account || '',
                      company: row.company || '',
                      transaction_type: row.transaction_type || '',
                    },
                  });
                }}
                className="rounded-2xl border border-border bg-white px-4 py-3"
                android_ripple={{ color: 'rgba(15,61,76,0.06)' }}
              >
                <View className="flex-row items-center justify-between">
                  <View className="flex-1 pr-3">
                    <Text className="text-body font-bold text-navy">{row.label}</Text>
                    <Text className="text-caption text-muted">
                      {[row.category, row.company || row.account, row.date]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                  </View>
                  <Text className="text-body font-extrabold text-navy">
                    {formatMoney(row.amount)}
                  </Text>
                </View>
              </Pressable>
            ))
          )}
        </>
      )}
    </ScrollView>
  );
}
