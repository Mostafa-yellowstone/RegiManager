import { type BottomSheetModal } from '@gorhom/bottom-sheet';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigation, useRouter } from 'expo-router';
import { useLayoutEffect, useMemo, useRef } from 'react';
import {
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AttendanceStrip } from '@/components/pulse/AttendanceStrip';
import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';
import { MetricCard } from '@/components/pulse/MetricCard';
import { RevenueChart } from '@/components/pulse/RevenueChart';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { TargetProgress } from '@/components/pulse/TargetProgress';
import { SpaceSwitcherSheet, SpaceSwitcherTrigger } from '@/components/space/SpaceSwitcher';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useSpaceStore } from '@/stores/spaceStore';
import type { DateRangePreset } from '@/types/models';

export default function PulseDashboardScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation();
  const router = useRouter();
  const sheetRef = useRef<BottomSheetModal>(null);
  const queryClient = useQueryClient();
  const { selectedOrg, organizations, selectOrganization, user } = useAuth();
  const selectedSpaceId = useSpaceStore((s) => s.selectedSpaceId);
  const setSelectedSpaceId = useSpaceStore((s) => s.setSelectedSpaceId);
  const preset = useDateRangeStore((s) => s.preset);
  const setPreset = useDateRangeStore((s) => s.setPreset);

  useLayoutEffect(() => {
    navigation.setOptions({ headerShown: false });
  }, [navigation]);

  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-dashboard', selectedOrg?.id, selectedSpaceId, preset],
    queryFn: () => getPulseDashboard(selectedSpaceId, preset),
    enabled: Boolean(selectedOrg?.id),
  });

  const agentsQuery = useQuery({
    queryKey: ['pulse-agents', selectedOrg?.id],
    queryFn: () => listOwnerAgents(),
    enabled: Boolean(selectedOrg?.id),
  });

  const spaceLabel = useMemo(() => {
    if (selectedSpaceId === 'all') return 'All Spaces';
    if (selectedSpaceId === 'dmv') return 'DMV';
    return data?.space_summaries.find((s) => s.space_id === selectedSpaceId)?.name ?? 'Space';
  }, [data?.space_summaries, selectedSpaceId]);

  const spaceOptions = useMemo(() => {
    const rows = data?.space_summaries ?? [];
    return [
      {
        id: 'all' as const,
        name: 'All Spaces',
        location: selectedOrg?.name || 'Organization rollup',
        revenue: data?.overview.net_profit || 0,
      },
      {
        id: 'dmv' as const,
        name: 'DMV',
        location: 'Processing fee · service records',
        revenue: data?.overview.dmv_net_profit || 0,
      },
      ...rows.map((r) => ({
        id: r.space_id,
        name: r.name,
        location: r.location,
        revenue: r.profit,
      })),
    ];
  }, [
    data?.overview.dmv_net_profit,
    data?.overview.net_profit,
    data?.space_summaries,
    selectedOrg?.name,
  ]);

  function onRangeChange(next: DateRangePreset) {
    setPreset(next);
  }

  async function onPickOrg() {
    if (organizations.length < 2) return;
    await hapticSelection();
    Alert.alert(
      'Switch location',
      'Choose a PSB organization',
      [
        ...organizations.map((org) => ({
          text: `${org.name}${org.city ? ` (${org.city})` : ''}`,
          onPress: () => {
            void (async () => {
              await selectOrganization(org.id);
              setSelectedSpaceId('all');
              await queryClient.invalidateQueries({ queryKey: ['pulse-dashboard'] });
              await queryClient.invalidateQueries({ queryKey: ['pulse-agents'] });
            })();
          },
        })),
        { text: 'Cancel', style: 'cancel' },
      ],
    );
  }

  const overview = data?.overview;
  const selectedSpaceKey = data?.space_summaries.find((s) => s.space_id === selectedSpaceId)?.key;
  const showDmvBlock = selectedSpaceId === 'all' || selectedSpaceId === 'dmv';
  const showInsuranceBlock = selectedSpaceId === 'all' || selectedSpaceKey === 'insurance';
  const showLobSection = showDmvBlock || showInsuranceBlock;

  return (
    <View className="flex-1 bg-cream" style={{ paddingTop: insets.top }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 120, gap: 16 }}
        refreshControl={
          <RefreshControl
            refreshing={isFetching && !isLoading}
            onRefresh={() => {
              void hapticLight();
              void refetch();
              void agentsQuery.refetch();
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <View className="gap-3">
          <View className="flex-row items-start justify-between gap-3">
            <View className="flex-1">
              <Text className="text-[11px] font-bold uppercase tracking-[2px] text-teal">
                RegiManager
              </Text>
              <Text
                style={{
                  fontSize: 36,
                  fontWeight: '800',
                  color: Colors.teal,
                  marginTop: 2,
                  letterSpacing: -0.8,
                }}
              >
                Pulse
              </Text>
              <Text className="mt-1 text-body text-muted">
                Owner overview · view & track only
              </Text>
              {user?.full_name ? (
                <Text className="mt-0.5 text-caption text-muted">{user.full_name}</Text>
              ) : null}
            </View>
            <View className="items-end gap-2">
              <Pressable
                onPress={() => {
                  void hapticLight();
                  router.push('/settings');
                }}
              >
                <Text className="text-caption font-bold text-teal">Settings</Text>
              </Pressable>
              {organizations.length > 1 ? (
                <Pressable onPress={onPickOrg}>
                  <Text className="text-caption font-bold text-teal">
                    {selectedOrg?.city || selectedOrg?.name || 'Location'}
                  </Text>
                </Pressable>
              ) : null}
              <SpaceSwitcherTrigger
                label={spaceLabel}
                onPress={() => {
                  void hapticLight();
                  sheetRef.current?.present();
                }}
              />
            </View>
          </View>

          <DateRangeSelector value={preset} onChange={onRangeChange} />
        </View>

        {isError ? (
          <View className="rounded-2xl border border-danger/30 bg-white p-4">
            <Text className="font-bold text-danger">Could not load live metrics</Text>
            <Text className="mt-1 text-caption text-muted">
              {(error as Error)?.message || 'Check your connection and owner permissions.'}
            </Text>
            <Pressable className="mt-3" onPress={() => void refetch()}>
              <Text className="font-semibold text-teal">Retry</Text>
            </Pressable>
          </View>
        ) : null}

        {isLoading || !overview ? (
          <View className="gap-3">
            <View className="flex-row flex-wrap gap-3">
              <SkeletonBlock height={120} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={120} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={120} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={120} className="min-w-[46%] flex-1" />
            </View>
            <SkeletonBlock height={220} />
          </View>
        ) : (
          <>
            {(agentsQuery.data?.agents?.length ?? 0) > 0 ? (
              <AttendanceStrip
                agents={agentsQuery.data?.agents ?? []}
                workDate={agentsQuery.data?.work_date}
                onSeeAll={() => router.push('/(tabs)/staff')}
              />
            ) : null}

            <View>
              <Text className="mb-3 text-title text-navy">Financial overview</Text>
              {!overview.cashflow_available && overview.cashflow_warning ? (
                <View
                  className="mb-3 rounded-xl px-3 py-2"
                  style={{ backgroundColor: Colors.orangeSoft }}
                >
                  <Text className="text-caption font-semibold" style={{ color: Colors.orangeDeep }}>
                    {overview.cashflow_warning}
                  </Text>
                </View>
              ) : null}
              <View className="flex-row flex-wrap gap-3">
                <MetricCard
                  label="Net profit"
                  value={overview.net_profit}
                  badge={overview.badges.profit}
                  accent="green"
                  metaLabel="ins + DMV"
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/sales');
                  }}
                />
                <MetricCard
                  label="Expenses"
                  value={overview.bank_expenses}
                  badge={overview.badges.expenses}
                  accent="orange"
                  metaLabel="bank txs"
                  metaValue={data?.costs?.length ?? 0}
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/expenses');
                  }}
                />
                <MetricCard
                  label="Cash flow"
                  value={overview.net_cash_flow}
                  accent="teal"
                  metaLabel="income − exp"
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/expenses');
                  }}
                />
                <MetricCard
                  label="Bank income"
                  value={overview.bank_income}
                  accent="purple"
                  metaLabel="finance income"
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/sales');
                  }}
                />
              </View>
              <Text className="mt-2 text-caption text-muted">
                Tap a card to open Sales or Expenses. Net profit = insurance + DMV. Cash flow = bank
                income − expenses.
              </Text>
            </View>

            {showLobSection ? (
              <View>
                <Text className="mb-3 text-title text-navy">
                  {selectedSpaceId === 'dmv'
                    ? 'DMV processing'
                    : selectedSpaceKey === 'insurance'
                      ? 'Insurance profit'
                      : 'By line of business'}
                </Text>
                <View className="flex-row flex-wrap gap-3">
                  {showDmvBlock ? (
                    <MetricCard
                      label="Processing fee"
                      value={overview.dmv_net_profit}
                      badge={overview.badges.dmv}
                      accent="teal"
                      metaLabel="records"
                      metaValue={overview.records_count}
                      onPress={() => {
                        void hapticSelection();
                        setSelectedSpaceId('dmv');
                      }}
                    />
                  ) : null}
                  {showInsuranceBlock ? (
                    <>
                      <MetricCard
                        label="Insurance profit"
                        value={overview.insurance_profit}
                        badge={overview.badges.insurance}
                        accent="green"
                        metaLabel="bound"
                        metaValue={overview.insurance_bound_count}
                        onPress={() => {
                          void hapticSelection();
                          const insurance = data?.space_summaries.find((s) => s.key === 'insurance');
                          if (insurance) setSelectedSpaceId(insurance.space_id);
                        }}
                      />
                      <MetricCard
                        label="Commission"
                        value={overview.insurance_commission}
                        accent="blue"
                        metaLabel="bound"
                        metaValue={overview.insurance_bound_count}
                        onPress={() => {
                          void hapticSelection();
                          const insurance = data?.space_summaries.find((s) => s.key === 'insurance');
                          if (insurance) setSelectedSpaceId(insurance.space_id);
                        }}
                      />
                      <MetricCard
                        label="Broker fees"
                        value={overview.insurance_broker_fee}
                        accent="orange"
                        metaLabel="bound"
                        metaValue={overview.insurance_bound_count}
                        onPress={() => {
                          void hapticSelection();
                          const insurance = data?.space_summaries.find((s) => s.key === 'insurance');
                          if (insurance) setSelectedSpaceId(insurance.space_id);
                        }}
                      />
                    </>
                  ) : null}
                </View>
                <Text className="mt-2 text-caption text-muted">
                  Processing fee matches CRM DMV profit. Insurance profit = commission + broker.
                  Expenses are banking only.
                </Text>
              </View>
            ) : null}

            {selectedSpaceId === 'all' ? (
              <View>
                <Text className="mb-3 text-title text-navy">Space profits</Text>
                <View className="gap-2">
                  {(data?.space_summaries ?? []).map((space) => (
                    <Pressable
                      key={space.space_id}
                      onPress={() => {
                        void hapticSelection();
                        setSelectedSpaceId(space.space_id);
                      }}
                      className="flex-row items-center justify-between rounded-2xl bg-white px-4 py-3"
                      style={{
                        borderWidth: 1,
                        borderColor: Colors.border,
                      }}
                      android_ripple={{ color: 'rgba(13,148,136,0.08)' }}
                    >
                      <View className="flex-1 pr-3">
                        <Text className="text-body font-bold text-navy">{space.name}</Text>
                        <Text className="text-caption text-muted">{space.location}</Text>
                      </View>
                      <Text className="text-body font-extrabold text-teal">
                        {formatMoney(space.profit)}
                      </Text>
                    </Pressable>
                  ))}
                </View>
                <Text className="mt-2 text-caption text-muted">Tap a space to filter the dashboard.</Text>
              </View>
            ) : null}

            <RevenueChart data={overview.series} />

            {(data?.targets?.length ?? 0) > 0 ? (
              <View>
                <Text className="mb-3 text-title text-navy">Goals & run rate</Text>
                <TargetProgress items={data?.targets ?? []} />
              </View>
            ) : null}
          </>
        )}
      </ScrollView>

      <SpaceSwitcherSheet
        ref={sheetRef}
        options={spaceOptions}
        selectedId={selectedSpaceId}
        onSelect={(id) => {
          setSelectedSpaceId(id);
          sheetRef.current?.dismiss();
        }}
      />
    </View>
  );
}
