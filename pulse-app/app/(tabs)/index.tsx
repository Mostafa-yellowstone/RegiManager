import BottomSheet from '@gorhom/bottom-sheet';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useRef } from 'react';
import {
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';
import { MetricCard } from '@/components/pulse/MetricCard';
import { RevenueChart } from '@/components/pulse/RevenueChart';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { TargetProgress } from '@/components/pulse/TargetProgress';
import { SpaceSwitcherSheet, SpaceSwitcherTrigger } from '@/components/space/SpaceSwitcher';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { formatMoney } from '@/lib/format';
import { hapticLight } from '@/lib/haptics';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useSpaceStore } from '@/stores/spaceStore';
import type { DateRangePreset } from '@/types/models';

export default function PulseDashboardScreen() {
  const insets = useSafeAreaInsets();
  const sheetRef = useRef<BottomSheet>(null);
  const selectedSpaceId = useSpaceStore((s) => s.selectedSpaceId);
  const setSelectedSpaceId = useSpaceStore((s) => s.setSelectedSpaceId);
  const preset = useDateRangeStore((s) => s.preset);
  const setPreset = useDateRangeStore((s) => s.setPreset);

  const { data, isLoading, isFetching, refetch, isError } = useQuery({
    queryKey: ['pulse-dashboard', selectedSpaceId, preset],
    queryFn: () => getPulseDashboard(selectedSpaceId, preset),
  });

  const spaceLabel = useMemo(() => {
    if (selectedSpaceId === 'all') return 'All spaces';
    return data?.space_summaries.find((s) => s.space_id === selectedSpaceId)?.name ?? 'Space';
  }, [data?.space_summaries, selectedSpaceId]);

  const spaceOptions = useMemo(() => {
    const rows = data?.space_summaries ?? [];
    return [
      {
        id: 'all' as const,
        name: 'All spaces combined',
        location: 'Organization rollup',
        revenue: rows.reduce((sum, r) => sum + r.revenue, 0),
      },
      ...rows.map((r) => ({
        id: r.space_id,
        name: r.name,
        location: r.location,
        revenue: r.revenue,
      })),
    ];
  }, [data?.space_summaries]);

  function onRangeChange(next: DateRangePreset) {
    if (next === 'custom') {
      Alert.alert('Custom range', 'Custom date picker lands in Phase 2. Using This Week for now.');
      setPreset('week');
      return;
    }
    setPreset(next);
  }

  const overview = data?.overview;

  return (
    <View className="flex-1 bg-cream" style={{ paddingBottom: insets.bottom }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 120, gap: 16 }}
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
        <View className="gap-3">
          <View className="flex-row items-start justify-between gap-3">
            <View className="flex-1">
              <Text className="text-caption font-bold uppercase tracking-widest text-muted">
                RegiManager
              </Text>
              <Text className="text-display text-navy">Pulse</Text>
              <Text className="mt-1 text-body text-muted">
                Owner overview · view & track only
              </Text>
            </View>
            <SpaceSwitcherTrigger
              label={spaceLabel}
              onPress={() => {
                void hapticLight();
                sheetRef.current?.expand();
              }}
            />
          </View>

          <DateRangeSelector value={preset} onChange={onRangeChange} />
        </View>

        {isError ? (
          <View className="rounded-2xl border border-danger/30 bg-white p-4">
            <Text className="font-bold text-danger">Could not load Pulse metrics</Text>
            <Pressable className="mt-3" onPress={() => void refetch()}>
              <Text className="font-semibold text-navy">Retry</Text>
            </Pressable>
          </View>
        ) : null}

        {isLoading || !overview ? (
          <View className="gap-3">
            <View className="flex-row flex-wrap gap-3">
              <SkeletonBlock height={112} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={112} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={112} className="min-w-[46%] flex-1" />
              <SkeletonBlock height={112} className="min-w-[46%] flex-1" />
            </View>
            <SkeletonBlock height={200} />
            <SkeletonBlock height={120} />
          </View>
        ) : (
          <>
            <View>
              <Text className="mb-3 text-title text-navy">Financial overview</Text>
              <View className="flex-row flex-wrap gap-3">
                <MetricCard
                  label="Gross revenue"
                  value={overview.gross_revenue}
                  deltaPct={overview.badges.revenue.delta_pct}
                  emphasize
                />
                <MetricCard
                  label="Total expenses"
                  value={overview.total_expenses}
                  deltaPct={overview.badges.expenses.delta_pct}
                />
                <MetricCard
                  label="Net profit"
                  value={overview.net_profit}
                  deltaPct={overview.badges.profit.delta_pct}
                  emphasize
                />
                <MetricCard
                  label="Profit margin"
                  value={overview.profit_margin_pct}
                  format="pct"
                  deltaPct={overview.badges.margin.delta_pct}
                />
              </View>
            </View>

            <RevenueChart data={overview.series} />

            <View>
              <Text className="mb-3 text-title text-navy">Targets & run rate</Text>
              <TargetProgress items={data?.targets ?? []} />
            </View>

            <View>
              <Text className="mb-3 text-title text-navy">Service intelligence</Text>
              <View className="gap-2">
                {(data?.services ?? []).map((svc) => (
                  <View
                    key={svc.service_id}
                    className="rounded-2xl border border-border bg-white px-4 py-3"
                  >
                    <View className="flex-row items-start justify-between gap-3">
                      <View className="flex-1">
                        <Text className="text-body font-bold text-navy">{svc.name}</Text>
                        <Text className="mt-0.5 text-caption text-muted">
                          {svc.category} · Peak {svc.peak_hour_label}
                        </Text>
                      </View>
                      <Text className="text-body font-extrabold text-navy">
                        {formatMoney(svc.revenue)}
                      </Text>
                    </View>
                    <View className="mt-3 flex-row justify-between">
                      <Text className="text-caption text-muted">{svc.bookings} bookings</Text>
                      <Text className="text-caption font-semibold text-navy">
                        Avg ticket {formatMoney(svc.avg_ticket)}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          </>
        )}
      </ScrollView>

      <SpaceSwitcherSheet
        ref={sheetRef}
        options={spaceOptions}
        selectedId={selectedSpaceId}
        onSelect={(id) => {
          setSelectedSpaceId(id);
          sheetRef.current?.close();
        }}
      />
    </View>
  );
}
