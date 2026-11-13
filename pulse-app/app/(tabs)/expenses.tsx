import { useQuery } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { RevenueChart } from '@/components/pulse/RevenueChart';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { getExpenseWatch } from '@/data/repositories/leaderboardRepository';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney, formatPct } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { usePulseScale } from '@/lib/responsive';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import type { CostFeeRow, ExpenseSegment } from '@/types/models';

type SegmentFilter = 'all' | ExpenseSegment;

const SEGMENT_TONE: Record<ExpenseSegment, { fg: string; bg: string; label: string }> = {
  dmv: { fg: Colors.blue, bg: Colors.blueSoft, label: 'DMV' },
  insurance: { fg: Colors.teal, bg: Colors.tealSoft, label: 'Insurance' },
};

export default function MoneyScreen() {
  const router = useRouter();
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const { pad } = usePulseScale();
  const [split, setSplit] = useState(false);
  const [segment, setSegment] = useState<SegmentFilter>('all');

  const dash = useQuery({
    queryKey: ['pulse-money', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => getPulseDashboard('all', preset),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 0,
  });
  const refetchMoney = dash.refetch;
  useFocusEffect(
    useCallback(() => {
      void refetchMoney();
    }, [refetchMoney]),
  );

  const overview = dash.data?.overview;
  const segments = dash.data?.expense_segments;
  const insurancePay = (overview?.insurance_commission || 0) + (overview?.insurance_broker_fee || 0);
  const allCosts = dash.data?.costs ?? [];
  const rows = useMemo(
    () => (segment === 'all' ? allCosts : allCosts.filter((row) => row.segment === segment)),
    [allCosts, segment],
  );
  const segmentTotal =
    segment === 'all'
      ? (segments?.dmv.total || 0) + (segments?.insurance.total || 0)
      : segments?.[segment].total || 0;
  const topCategories = useMemo(() => topCategoriesOf(rows), [rows]);

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: pad, paddingTop: 12, paddingBottom: 120, gap: 12 }}
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
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <SegmentChip
            label="All"
            amount={(segments?.dmv.total || 0) + (segments?.insurance.total || 0)}
            active={segment === 'all'}
            onPress={() => setSegment('all')}
          />
          <SegmentChip
            label="DMV"
            amount={segments?.dmv.total || 0}
            tone={SEGMENT_TONE.dmv.fg}
            active={segment === 'dmv'}
            onPress={() => setSegment('dmv')}
          />
          <SegmentChip
            label="Insurance"
            amount={segments?.insurance.total || 0}
            tone={SEGMENT_TONE.insurance.fg}
            active={segment === 'insurance'}
            onPress={() => setSegment('insurance')}
          />
        </View>

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
            <View style={card}>
              <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                {segment === 'all' ? 'All expenses' : `${SEGMENT_TONE[segment].label} expenses`}
              </Text>
              <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 26, color: Colors.navy }}>
                {formatMoney(segmentTotal)}
              </Text>
              <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                {segment === 'all'
                  ? `DMV ${formatMoney(segments?.dmv.total || 0)} · Insurance ${formatMoney(segments?.insurance.total || 0)}`
                  : `${segments?.[segment].count || 0} entries in this range`}
              </Text>
              {topCategories.length ? (
                <View style={{ marginTop: 12, gap: 8 }}>
                  {topCategories.map((cat) => (
                    <View key={cat.name} style={{ gap: 4 }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                        <Text style={{ fontFamily: Fonts.semibold, fontSize: 12, color: Colors.navyMid }} numberOfLines={1}>
                          {cat.name}
                        </Text>
                        <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.navy }}>
                          {formatMoney(cat.amount)}
                        </Text>
                      </View>
                      <View style={{ height: 5, borderRadius: 3, backgroundColor: Colors.navySoft }}>
                        <View
                          style={{
                            height: 5,
                            borderRadius: 3,
                            width: `${Math.max(4, cat.share * 100)}%`,
                            backgroundColor: segment === 'all' ? Colors.orange : SEGMENT_TONE[segment].fg,
                          }}
                        />
                      </View>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>

            <ExpenseWatchCard
              segment={segment}
              onEdit={() => {
                void hapticSelection();
                router.push('/settings' as any);
              }}
            />

            {segment !== 'dmv' ? (
              <>
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <MoneyCard label="Bank in" value={formatMoney(overview.bank_income)} />
                  <MoneyCard label="Bank out" value={formatMoney(overview.bank_expenses)} />
                  <MoneyCard label="What's left" value={formatMoney(overview.net_cash_flow)} />
                </View>
                {typeof overview.left_delta_pct === 'number' ? (
                  <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
                    What's left {formatPct(overview.left_delta_pct, 0)} versus the previous period
                  </Text>
                ) : null}
              </>
            ) : null}

            <View style={card}>
              {segment !== 'insurance' ? (
                <Line label="DMV profit" value={formatMoney(overview.dmv_net_profit)} />
              ) : null}
              {segment === 'dmv' ? (
                <View style={{ marginTop: 8 }}>
                  <Line
                    label="After DMV expenses"
                    value={formatMoney(overview.dmv_net_profit - (segments?.dmv.total || 0))}
                    muted
                  />
                </View>
              ) : null}
              {segment !== 'dmv' ? (
                <>
                  <Pressable
                    onPress={() => {
                      void hapticSelection();
                      setSplit((open) => !open);
                    }}
                    style={{ marginTop: segment === 'all' ? 12 : 0 }}
                  >
                    <Line
                      label="Insurance profit"
                      value={formatMoney(insurancePay)}
                      hint={split ? 'Hide split' : 'Show split'}
                    />
                  </Pressable>
                  {split ? (
                    <View style={{ marginTop: 8, gap: 6 }}>
                      <Line label="Commission" value={formatMoney(overview.insurance_commission)} muted />
                      <Line label="Broker fee" value={formatMoney(overview.insurance_broker_fee)} muted />
                    </View>
                  ) : null}
                </>
              ) : null}
            </View>

            {segment !== 'dmv' && !overview.cashflow_available && overview.cashflow_warning ? (
              <Text style={{ fontFamily: Fonts.semibold, fontSize: 13, color: Colors.orangeDeep }}>
                {overview.cashflow_warning}
              </Text>
            ) : null}

            {segment === 'all' ? <RevenueChart data={overview.series} /> : null}

            <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>
              {segment === 'all' ? 'Money out' : `${SEGMENT_TONE[segment].label} expenses`}
            </Text>
            {rows.length === 0 ? (
              <Text style={{ fontFamily: Fonts.medium, color: Colors.muted }}>No expenses in this range.</Text>
            ) : (
              rows.map((row) => <ExpenseRow key={`${row.segment}-${row.id}`} row={row} onOpen={() => {
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
                    segment: row.segment,
                  },
                });
              }} />)
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function ExpenseWatchCard({ segment, onEdit }: { segment: SegmentFilter; onEdit: () => void }) {
  const { selectedOrg } = useAuth();
  const watch = useQuery({
    queryKey: ['pulse-expense-watch', selectedOrg?.id],
    queryFn: () => getExpenseWatch(),
    enabled: Boolean(selectedOrg?.id),
  });
  const data = watch.data;
  if (!data) return null;
  const rows = data.categories
    .filter((row) => segment === 'all' || row.segment === segment)
    .filter((row) => row.this_month > 0 || row.last_month > 0)
    .slice(0, 5);
  const overCount = data.categories.filter(
    (row) => row.over && (segment === 'all' || row.segment === segment),
  ).length;
  const { settings } = data;

  return (
    <View style={card}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>Expense watch</Text>
          <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            This month so far vs all of last month
          </Text>
        </View>
        {overCount > 0 ? (
          <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: Colors.orangeSoft }}>
            <Text style={{ fontFamily: Fonts.extrabold, fontSize: 11, color: Colors.orangeDeep }}>
              {overCount} over
            </Text>
          </View>
        ) : null}
      </View>

      {rows.length === 0 ? (
        <Text style={{ marginTop: 10, fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
          No expenses this month or last month yet.
        </Text>
      ) : (
        <View style={{ marginTop: 12, gap: 10 }}>
          {rows.map((row) => {
            const up = (row.change_pct ?? 0) > 0;
            const tone = row.over ? Colors.orangeDeep : up ? Colors.navyMid : Colors.greenDeep;
            return (
              <View
                key={`${row.segment}-${row.category}`}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}
              >
                <View
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 4,
                    backgroundColor: SEGMENT_TONE[row.segment].fg,
                  }}
                />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text numberOfLines={1} style={{ fontFamily: Fonts.semibold, fontSize: 13, color: Colors.navy }}>
                    {row.category}
                  </Text>
                  <Text style={{ fontFamily: Fonts.medium, fontSize: 11, color: Colors.muted }}>
                    {formatMoney(row.this_month)} vs {formatMoney(row.last_month)}
                  </Text>
                </View>
                <Text style={{ fontFamily: Fonts.extrabold, fontSize: 13, color: tone }}>
                  {row.change_pct == null ? 'New' : `${up ? '+' : ''}${row.change_pct.toFixed(0)}%`}
                </Text>
              </View>
            );
          })}
        </View>
      )}

      <Pressable onPress={onEdit} style={{ marginTop: 12 }}>
        <Text style={{ fontFamily: Fonts.semibold, fontSize: 12, color: Colors.teal }}>
          {settings.enabled
            ? `Alerts on: one expense ≥ ${formatMoney(settings.single_expense_limit)} or a category +${settings.category_jump_percent}% · Edit`
            : 'Expense alerts are off · Turn on in Settings'}
        </Text>
      </Pressable>
    </View>
  );
}

function topCategoriesOf(rows: CostFeeRow[]) {
  const totals = new Map<string, number>();
  for (const row of rows) {
    totals.set(row.category, (totals.get(row.category) || 0) + row.amount);
  }
  const grand = Array.from(totals.values()).reduce((sum, value) => sum + value, 0);
  return Array.from(totals.entries())
    .map(([name, amount]) => ({ name, amount, share: grand > 0 ? amount / grand : 0 }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 4);
}

function SegmentChip({
  label,
  amount,
  active,
  tone,
  onPress,
}: {
  label: string;
  amount: number;
  active: boolean;
  tone?: string;
  onPress: () => void;
}) {
  const accent = tone || Colors.orange;
  return (
    <Pressable
      onPress={() => {
        void hapticSelection();
        onPress();
      }}
      accessibilityRole="button"
      accessibilityState={active ? { selected: true } : {}}
      style={{
        flex: 1,
        borderRadius: 14,
        paddingVertical: 10,
        paddingHorizontal: 10,
        backgroundColor: active ? Colors.navySoft : Colors.white,
        borderWidth: 1,
        borderColor: active ? accent : Colors.border,
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: accent }} />
        <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: active ? Colors.navy : Colors.muted }}>
          {label}
        </Text>
      </View>
      <Text
        adjustsFontSizeToFit
        minimumFontScale={0.7}
        numberOfLines={1}
        style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }}
      >
        {formatMoney(amount)}
      </Text>
    </Pressable>
  );
}

function ExpenseRow({ row, onOpen }: { row: CostFeeRow; onOpen: () => void }) {
  const tone = SEGMENT_TONE[row.segment];
  return (
    <Pressable onPress={onOpen} style={card}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }} numberOfLines={2}>
            {row.label}
          </Text>
          <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, backgroundColor: tone.bg }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 10, color: tone.fg }}>{tone.label}</Text>
            </View>
            <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
              {[row.category, row.date].filter(Boolean).join(' · ')}
            </Text>
          </View>
        </View>
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }}>
          {formatMoney(row.amount)}
        </Text>
      </View>
    </Pressable>
  );
}

function MoneyCard({ label, value }: { label: string; value: string }) {
  const { fs, isLandscape } = usePulseScale();
  return (
    <View style={[card, { flexGrow: 1, flexBasis: isLandscape ? '22%' : '30%', minWidth: 96 }]}>
      <Text style={{ fontFamily: Fonts.medium, fontSize: fs(12), color: Colors.muted }}>{label}</Text>
      <Text
        adjustsFontSizeToFit
        minimumFontScale={0.65}
        numberOfLines={1}
        style={{ marginTop: 6, fontFamily: Fonts.extrabold, fontSize: fs(18), color: Colors.navy }}
      >
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
  const { fs } = usePulseScale();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <Text style={{ flex: 1, fontFamily: muted ? Fonts.medium : Fonts.bold, fontSize: fs(muted ? 13 : 15), color: muted ? Colors.muted : Colors.navy }}>
        {label}
      </Text>
      <View style={{ alignItems: 'flex-end', flexShrink: 1 }}>
        <Text
          adjustsFontSizeToFit
          minimumFontScale={0.7}
          numberOfLines={1}
          style={{ fontFamily: Fonts.extrabold, fontSize: fs(muted ? 14 : 16), color: Colors.navy }}
        >
          {value}
        </Text>
        {hint ? (
          <Text style={{ fontFamily: Fonts.bold, fontSize: fs(11), color: Colors.teal }}>{hint}</Text>
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
