import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { RevenueChart } from '@/components/pulse/RevenueChart';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney, formatPct } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';

export default function MoneyScreen() {
  const router = useRouter();
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const [split, setSplit] = useState(false);

  const dash = useQuery({
    queryKey: ['pulse-money', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => getPulseDashboard('all', preset),
    enabled: Boolean(selectedOrg?.id),
  });

  const overview = dash.data?.overview;
  const insurancePay = (overview?.insurance_commission || 0) + (overview?.insurance_broker_fee || 0);

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 120, gap: 12 }}
        refreshControl={
          <RefreshControl
            refreshing={dash.isFetching && !dash.isLoading}
            onRefresh={() => {
              void hapticLight();
              void dash.refetch();
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <ConnectedDateRangeSelector />
        {dash.isError ? (
          <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
            {(dash.error as Error)?.message || 'Could not load money'}
          </Text>
        ) : null}
        {dash.isLoading || !overview ? (
          <>
            <SkeletonBlock height={110} />
            <SkeletonBlock height={180} />
          </>
        ) : (
          <>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <MoneyCard label="Money in" value={formatMoney(overview.bank_income)} />
              <MoneyCard label="Money out" value={formatMoney(overview.bank_expenses)} />
              <MoneyCard label="What's left" value={formatMoney(overview.net_cash_flow)} />
            </View>
            {typeof overview.left_delta_pct === 'number' ? (
              <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
                What's left {formatPct(overview.left_delta_pct, 0)} versus the previous period
              </Text>
            ) : null}

            <View style={card}>
              <Line label="DMV Profit" value={formatMoney(overview.dmv_net_profit)} />
              <Pressable
                onPress={() => {
                  void hapticSelection();
                  setSplit((open) => !open);
                }}
                style={{ marginTop: 12 }}
              >
                <Line label="Insurance pay" value={formatMoney(insurancePay)} hint={split ? 'Hide split' : 'Show split'} />
              </Pressable>
              {split ? (
                <View style={{ marginTop: 8, gap: 6 }}>
                  <Line label="Commission" value={formatMoney(overview.insurance_commission)} muted />
                  <Line label="Broker fee" value={formatMoney(overview.insurance_broker_fee)} muted />
                </View>
              ) : null}
            </View>

            {!overview.cashflow_available && overview.cashflow_warning ? (
              <Text style={{ fontFamily: Fonts.semibold, fontSize: 13, color: Colors.orangeDeep }}>
                {overview.cashflow_warning}
              </Text>
            ) : null}

            <RevenueChart data={overview.series} />

            <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>Money out</Text>
            {(dash.data?.costs ?? []).length === 0 ? (
              <Text style={{ fontFamily: Fonts.medium, color: Colors.muted }}>No bank lines in this range.</Text>
            ) : (
              (dash.data?.costs ?? []).map((row) => (
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
                  style={card}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }} numberOfLines={2}>
                        {row.label}
                      </Text>
                      <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                        {[row.category, row.date].filter(Boolean).join(' · ')}
                      </Text>
                    </View>
                    <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }}>
                      {formatMoney(row.amount)}
                    </Text>
                  </View>
                </Pressable>
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function MoneyCard({ label, value }: { label: string; value: string }) {
  return (
    <View style={[card, { flex: 1 }]}>
      <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>{label}</Text>
      <Text style={{ marginTop: 6, fontFamily: Fonts.extrabold, fontSize: 16, color: Colors.navy }} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function Line({
  label,
  value,
  hint,
  muted,
}: {
  label: string;
  value: string;
  hint?: string;
  muted?: boolean;
}) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <Text style={{ fontFamily: muted ? Fonts.medium : Fonts.bold, fontSize: muted ? 13 : 15, color: muted ? Colors.muted : Colors.navy }}>
        {label}
      </Text>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: muted ? 14 : 16, color: Colors.navy }}>{value}</Text>
        {hint ? (
          <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.teal }}>{hint}</Text>
        ) : null}
      </View>
    </View>
  );
}

const card = {
  backgroundColor: Colors.white,
  borderRadius: 16,
  borderWidth: 1,
  borderColor: Colors.border,
  padding: 14,
};
