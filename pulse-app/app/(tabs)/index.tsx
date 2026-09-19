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
import { AttentionInbox } from '@/components/pulse/AttentionInbox';
import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';
import { HeaderActions } from '@/components/pulse/HeaderActions';
import { MetricCard } from '@/components/pulse/MetricCard';
import { MetricGrid } from '@/components/pulse/MetricGrid';
import { MorningBrief } from '@/components/pulse/MorningBrief';
import { RevenueChart } from '@/components/pulse/RevenueChart';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { TargetProgress } from '@/components/pulse/TargetProgress';
import { SpaceSwitcherSheet, SpaceSwitcherTrigger } from '@/components/space/SpaceSwitcher';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { listSalesActivity } from '@/data/repositories/salesRepository';
import { useAuth } from '@/lib/auth';
import { crmFinanceUrl, crmHomeUrl, openCrmUrl } from '@/lib/crmLinks';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { buildAttentionItems, buildMorningBrief, orgHasInsuranceSpace, spaceInsight } from '@/lib/ownerInsights';
import { Colors, Fonts } from '@/lib/theme';
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

  const briefQuery = useQuery({
    queryKey: ['pulse-brief-yesterday', selectedOrg?.id],
    queryFn: () => getPulseDashboard('all', 'yesterday'),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 60_000,
  });

  const salesQuery = useQuery({
    queryKey: ['pulse-sales', selectedOrg?.id, preset],
    queryFn: () => listSalesActivity(preset),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 30_000,
  });

  const morningBrief = useMemo(
    () =>
      buildMorningBrief({
        overview: briefQuery.data?.overview,
        agents: agentsQuery.data?.agents,
        workDate: agentsQuery.data?.work_date,
        asOfLabel: 'Yesterday · owner snapshot',
        hasInsurance: orgHasInsuranceSpace(data?.space_summaries),
        spaceSummaries: data?.space_summaries,
      }),
    [
      agentsQuery.data?.agents,
      agentsQuery.data?.work_date,
      briefQuery.data?.overview,
      data?.space_summaries,
    ],
  );

  const attentionItems = useMemo(
    () =>
      buildAttentionItems({
        overview: data?.overview,
        agents: agentsQuery.data?.agents,
        salesCount: salesQuery.data ? salesQuery.data.length : null,
        spaceSummaries: data?.space_summaries,
      }),
    [agentsQuery.data?.agents, data?.overview, data?.space_summaries, salesQuery.data],
  );

  const sortedAgents = useMemo(() => {
    const agents = [...(agentsQuery.data?.agents ?? [])];
    agents.sort((a, b) => {
      if (a.is_late !== b.is_late) return Number(b.is_late) - Number(a.is_late);
      if (a.attendance_open !== b.attendance_open) {
        return Number(b.attendance_open) - Number(a.attendance_open);
      }
      return a.name.localeCompare(b.name);
    });
    return agents;
  }, [agentsQuery.data?.agents]);

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
              void briefQuery.refetch();
              void salesQuery.refetch();
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <View style={{ gap: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <View style={{ flex: 1, minWidth: 0, paddingRight: 4 }}>
              <Text
                style={{
                  fontFamily: Fonts.bold,
                  fontSize: 11,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  color: Colors.teal,
                }}
              >
                RegiManager
              </Text>
              <Text
                style={{
                  fontFamily: Fonts.extrabold,
                  fontSize: 34,
                  color: Colors.teal,
                  marginTop: 2,
                  letterSpacing: -0.8,
                }}
              >
                Pulse
              </Text>
              {user?.full_name ? (
                <Text
                  numberOfLines={1}
                  style={{
                    marginTop: 8,
                    fontFamily: Fonts.extrabold,
                    fontSize: 20,
                    color: Colors.navy,
                    letterSpacing: -0.3,
                  }}
                >
                  {user.full_name}
                </Text>
              ) : null}
              <Text
                style={{
                  marginTop: 4,
                  fontFamily: Fonts.medium,
                  fontSize: 13,
                  color: Colors.muted,
                }}
              >
                Owner command layer
              </Text>
              {selectedOrg ? (
                <Pressable
                  style={{
                    marginTop: 10,
                    alignSelf: 'flex-start',
                    borderRadius: 999,
                    paddingHorizontal: 12,
                    paddingVertical: 7,
                    backgroundColor: Colors.navySoft,
                    borderWidth: 1,
                    borderColor: Colors.border,
                  }}
                  onPress={() => {
                    if (organizations.length > 1) void onPickOrg();
                  }}
                >
                  <Text style={{ fontFamily: Fonts.extrabold, fontSize: 11, color: Colors.navy }}>
                    {selectedOrg.city
                      ? `${selectedOrg.name} · ${selectedOrg.city}`
                      : selectedOrg.name}
                    {organizations.length > 1 ? ' ▾' : ''}
                  </Text>
                </Pressable>
              ) : null}
            </View>
            <HeaderActions
              onSettings={() => {
                void hapticLight();
                router.push('/settings');
              }}
              onOpenCrm={() => {
                void hapticLight();
                void openCrmUrl(crmHomeUrl());
              }}
            />
          </View>

          <View style={{ gap: 10 }}>
            <DateRangeSelector value={preset} onChange={onRangeChange} />
            <View style={{ flexDirection: 'row', justifyContent: 'flex-start' }}>
              <SpaceSwitcherTrigger
                label={spaceLabel}
                onPress={() => {
                  void hapticLight();
                  sheetRef.current?.present();
                }}
              />
            </View>
          </View>
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

        {!selectedOrg?.id ? (
          <View className="rounded-2xl border border-border bg-white p-4">
            <Text className="font-bold text-navy">No owner organization</Text>
            <Text className="mt-1 text-caption text-muted">
              Sign in again with an organization owner account to load Pulse metrics.
            </Text>
          </View>
        ) : isLoading || !overview ? (
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
            {morningBrief ? (
              <MorningBrief
                brief={morningBrief}
                onOpenStaff={() => router.push('/(tabs)/staff')}
                onOpenExpenses={() => router.push('/(tabs)/expenses')}
              />
            ) : briefQuery.isLoading ? (
              <SkeletonBlock height={190} />
            ) : null}

            <AttentionInbox
              items={attentionItems}
              onOpen={(item) => {
                void hapticSelection();
                router.push(item.href as any);
              }}
            />

            {sortedAgents.length > 0 ? (
              <AttendanceStrip
                agents={sortedAgents}
                workDate={agentsQuery.data?.work_date}
                onSeeAll={() => router.push('/(tabs)/staff')}
              />
            ) : null}

            <View style={{ gap: 10 }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>
                Financial overview
              </Text>
              <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted, lineHeight: 17 }}>
                Profit = insurance + DMV. Cash = bank income − expenses. Don’t mix them.
              </Text>
              {!overview.cashflow_available && overview.cashflow_warning ? (
                <View
                  style={{
                    borderRadius: 12,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    backgroundColor: Colors.orangeSoft,
                  }}
                >
                  <Text style={{ fontFamily: Fonts.semibold, fontSize: 12, color: Colors.orangeDeep }}>
                    {overview.cashflow_warning}
                  </Text>
                </View>
              ) : null}
              <MetricGrid>
                <MetricCard
                  label="Net profit"
                  value={overview.net_profit}
                  badge={overview.badges.profit}
                  accent="green"
                  metaLabel="ins + DMV"
                  hint="Operating profit"
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
                  hint="Bank outflows"
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
                  hint="Bank cash movement"
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/expenses');
                  }}
                />
                <MetricCard
                  label="Bank income"
                  value={overview.bank_income}
                  accent="teal"
                  metaLabel="finance income"
                  hint="Bank inflows"
                  onPress={() => {
                    void hapticSelection();
                    router.push('/(tabs)/sales');
                  }}
                />
              </MetricGrid>
              <Pressable
                onPress={() => {
                  void hapticLight();
                  void openCrmUrl(crmFinanceUrl());
                }}
                style={{
                  alignSelf: 'flex-start',
                  marginTop: 2,
                  paddingVertical: 6,
                }}
              >
                <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.teal }}>
                  Review in CRM Finance →
                </Text>
              </Pressable>
            </View>

            {showLobSection ? (
              <View style={{ gap: 10, marginTop: 4 }}>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>
                  {selectedSpaceId === 'dmv'
                    ? 'DMV processing'
                    : selectedSpaceKey === 'insurance'
                      ? 'Insurance profit'
                      : 'By line of business'}
                </Text>
                <MetricGrid>
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
                        if (insurance) {
                          setSelectedSpaceId(insurance.space_id);
                        } else {
                          Alert.alert(
                            'Insurance space',
                            'No insurance space is available for this organization yet.',
                          );
                        }
                      }}
                    />
                  ) : null}
                  {showInsuranceBlock ? (
                    <MetricCard
                      label="Commission"
                      value={overview.insurance_commission}
                      accent="teal"
                      metaLabel="bound"
                      metaValue={overview.insurance_bound_count}
                      onPress={() => {
                        void hapticSelection();
                        const insurance = data?.space_summaries.find((s) => s.key === 'insurance');
                        if (insurance) {
                          setSelectedSpaceId(insurance.space_id);
                        } else {
                          Alert.alert(
                            'Insurance space',
                            'No insurance space is available for this organization yet.',
                          );
                        }
                      }}
                    />
                  ) : null}
                  {showInsuranceBlock ? (
                    <MetricCard
                      label="Broker fees"
                      value={overview.insurance_broker_fee}
                      accent="orange"
                      metaLabel="bound"
                      metaValue={overview.insurance_bound_count}
                      onPress={() => {
                        void hapticSelection();
                        const insurance = data?.space_summaries.find((s) => s.key === 'insurance');
                        if (insurance) {
                          setSelectedSpaceId(insurance.space_id);
                        } else {
                          Alert.alert(
                            'Insurance space',
                            'No insurance space is available for this organization yet.',
                          );
                        }
                      }}
                    />
                  ) : null}
                </MetricGrid>
                <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted, lineHeight: 17 }}>
                  Processing fee matches CRM DMV profit. Insurance profit = commission + broker.
                  Expenses are banking only.
                </Text>
              </View>
            ) : null}

            {selectedSpaceId === 'all' ? (
              <View style={{ gap: 10 }}>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>
                  Space scorecards
                </Text>
                <View style={{ gap: 8 }}>
                  {(data?.space_summaries ?? []).map((space) => (
                    <Pressable
                      key={space.space_id}
                      onPress={() => {
                        void hapticSelection();
                        setSelectedSpaceId(space.space_id);
                      }}
                      style={{
                        borderRadius: 16,
                        backgroundColor: Colors.white,
                        paddingHorizontal: 16,
                        paddingVertical: 12,
                        borderWidth: 1,
                        borderColor: Colors.border,
                      }}
                      android_ripple={{ color: 'rgba(13,148,136,0.08)' }}
                    >
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <View style={{ flex: 1, paddingRight: 12, minWidth: 0 }}>
                          <Text
                            numberOfLines={1}
                            style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}
                          >
                            {space.name}
                          </Text>
                          <Text
                            numberOfLines={1}
                            style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}
                          >
                            {space.location}
                          </Text>
                          <Text
                            numberOfLines={1}
                            style={{
                              marginTop: 4,
                              fontFamily: Fonts.bold,
                              fontSize: 11,
                              color: Colors.teal,
                            }}
                          >
                            {spaceInsight(space)}
                          </Text>
                        </View>
                        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.teal }}>
                          {formatMoney(space.profit)}
                        </Text>
                      </View>
                    </Pressable>
                  ))}
                </View>
                <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                  Tap a space to filter the dashboard.
                </Text>
              </View>
            ) : null}

            <RevenueChart data={overview.series} />

            {(data?.targets?.length ?? 0) > 0 ? (
              <View style={{ gap: 10 }}>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>
                  Goals & run rate
                </Text>
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
