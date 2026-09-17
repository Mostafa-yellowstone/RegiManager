import { useQuery } from '@tanstack/react-query';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listSalesActivity } from '@/data/repositories/salesRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import type { DateRangePreset } from '@/types/models';

export default function SalesScreen() {
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const setPreset = useDateRangeStore((s) => s.setPreset);
  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-sales', selectedOrg?.id, preset],
    queryFn: () => listSalesActivity(preset),
    enabled: Boolean(selectedOrg?.id),
  });

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
      <Text className="text-title text-navy">Sales activity</Text>
      <Text className="mb-1 text-caption text-muted">
        Live DMV and insurance payments — view only (no tap actions on rows)
      </Text>
      <DateRangeSelector value={preset} onChange={(next: DateRangePreset) => setPreset(next)} />

      {isError ? (
        <Text className="text-caption font-semibold text-danger">
          {(error as Error)?.message || 'Failed to load sales'}
        </Text>
      ) : null}

      {isLoading ? (
        <>
          <SkeletonBlock height={72} />
          <SkeletonBlock height={72} />
          <SkeletonBlock height={72} />
        </>
      ) : (data?.length ?? 0) === 0 ? (
        <Text className="mt-6 text-center text-body text-muted">No payments in this range.</Text>
      ) : (
        data?.map((row) => (
          <View
            key={row.id}
            className="rounded-xl bg-cream px-3 py-3"
            style={{ borderWidth: 1, borderColor: Colors.border }}
          >
            <View className="flex-row items-start justify-between gap-3">
              <View className="flex-1">
                <Text className="text-body font-bold text-navy">{row.title}</Text>
                <Text className="mt-0.5 text-caption text-muted">
                  {row.category} · {row.subtitle}
                </Text>
              </View>
              <Text className="text-body font-extrabold text-navy">{formatMoney(row.amount)}</Text>
            </View>
            {row.date ? <Text className="mt-2 text-caption text-muted">{row.date}</Text> : null}
          </View>
        ))
      )}
    </ScrollView>
  );
}
