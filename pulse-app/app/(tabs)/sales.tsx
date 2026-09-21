import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listSalesActivity } from '@/data/repositories/salesRepository';
import { useAuth } from '@/lib/auth';
import { crmHomeUrl, openCrmUrl } from '@/lib/crmLinks';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import type { ActivityRow } from '@/types/models';

function categoryStyle(category: string): { bg: string; fg: string; label: string } {
  const key = (category || '').toLowerCase();
  if (key.includes('dmv') || key.includes('processing')) {
    return { bg: Colors.tealSoft, fg: Colors.tealDeep, label: category || 'DMV' };
  }
  if (key.includes('insur') || key.includes('policy') || key.includes('bound')) {
    return { bg: Colors.greenSoft, fg: Colors.greenDeep, label: category || 'Insurance' };
  }
  if (key.includes('motor') || key.includes('roadside')) {
    return { bg: Colors.orangeSoft, fg: Colors.orangeDeep, label: category || 'Motor Club' };
  }
  if (key.includes('payment') || key.includes('renew')) {
    return { bg: Colors.blueSoft, fg: '#1D4ED8', label: category || 'Payment' };
  }
  return { bg: Colors.navySoft, fg: Colors.navy, label: category || 'Sale' };
}

function SalesRow({ row }: { row: ActivityRow }) {
  const badge = categoryStyle(row.category);
  return (
    <View
      className="rounded-2xl bg-white px-4 py-3.5"
      style={{
        borderWidth: 1,
        borderColor: Colors.border,
        shadowColor: '#0F3D4C',
        shadowOpacity: 0.04,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 2 },
        elevation: 1,
      }}
    >
      <View className="flex-row items-start justify-between gap-3">
        <View className="flex-1 pr-2">
          <View className="mb-2 flex-row flex-wrap items-center gap-2">
            <View className="rounded-full px-2.5 py-1" style={{ backgroundColor: badge.bg }}>
              <Text className="text-[11px] font-extrabold" style={{ color: badge.fg }}>
                {badge.label}
              </Text>
            </View>
            {row.date ? (
              <Text className="text-[11px] font-bold text-muted">{row.date}</Text>
            ) : null}
          </View>
          <Text className="text-body font-bold text-navy" numberOfLines={2}>
            {row.title}
          </Text>
          {row.subtitle ? (
            <Text className="mt-1 text-caption text-muted" numberOfLines={2}>
              {row.subtitle}
            </Text>
          ) : null}
        </View>
        <Text className="text-[17px] font-extrabold text-teal">{formatMoney(row.amount)}</Text>
      </View>
    </View>
  );
}

export default function SalesScreen() {
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-sales', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => listSalesActivity(preset),
    enabled: Boolean(selectedOrg?.id),
  });

  const summary = useMemo(() => {
    const rows = data ?? [];
    const total = rows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
    const byCategory = new Map<string, number>();
    for (const row of rows) {
      const key = (row.category || 'Other').trim() || 'Other';
      byCategory.set(key, (byCategory.get(key) || 0) + (Number(row.amount) || 0));
    }
    const topCategories = [...byCategory.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, amount]) => ({ label, amount, style: categoryStyle(label) }));
    return { total, count: rows.length, topCategories };
  }, [data]);

  const filteredRows = useMemo(() => {
    const rows = data ?? [];
    if (categoryFilter === 'all') return rows;
    return rows.filter((row) => (row.category || 'Other').trim() === categoryFilter);
  }, [categoryFilter, data]);

  return (
    <ScrollView
      className="flex-1 bg-cream"
      contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 12 }}
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
      <Text className="text-caption text-muted">
        Live DMV and insurance payments for the selected range. View only.
      </Text>
      <ConnectedDateRangeSelector />

      {!selectedOrg?.id ? (
        <Text className="mt-4 text-center text-body text-muted">
          No owner organization selected.
        </Text>
      ) : null}

      {isError ? (
        <View
          className="rounded-2xl bg-white px-4 py-3"
          style={{ borderWidth: 1, borderColor: '#FECACA' }}
        >
          <Text className="text-caption font-semibold text-danger">
            {(error as Error)?.message || 'Failed to load sales'}
          </Text>
        </View>
      ) : null}

      {isLoading ? (
        <>
          <SkeletonBlock height={96} />
          <SkeletonBlock height={88} />
          <SkeletonBlock height={88} />
        </>
      ) : (data?.length ?? 0) === 0 ? (
        <View
          className="mt-2 items-center rounded-2xl bg-white px-4 py-8"
          style={{ borderWidth: 1, borderColor: Colors.border }}
        >
          <Text className="text-body font-bold text-navy">No payments in this range</Text>
          <Text className="mt-1 text-center text-caption text-muted">
            Try another date range or open the CRM to review live activity.
          </Text>
          <Pressable
            className="mt-3"
            onPress={() => {
              void hapticSelection();
              void openCrmUrl(crmHomeUrl());
            }}
          >
            <Text className="text-caption font-bold text-teal">Open CRM →</Text>
          </Pressable>
        </View>
      ) : (
        <>
          <View
            className="rounded-2xl bg-white p-4"
            style={{ borderWidth: 1, borderColor: Colors.border }}
          >
            <Text className="text-[11px] font-bold uppercase tracking-wide text-muted">
              Total in range
            </Text>
            <Text className="mt-1 text-[28px] font-extrabold text-navy">
              {formatMoney(summary.total)}
            </Text>
            <Text className="mt-1 text-caption text-muted">
              {summary.count} payment{summary.count === 1 ? '' : 's'}
            </Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              className="mt-3 grow-0"
              contentContainerStyle={{ gap: 8 }}
            >
              <Pressable
                onPress={() => {
                  void hapticSelection();
                  setCategoryFilter('all');
                }}
                className="rounded-full px-3 py-1.5"
                style={{
                  backgroundColor: categoryFilter === 'all' ? Colors.navy : Colors.cream,
                  borderWidth: 1,
                  borderColor: categoryFilter === 'all' ? Colors.navy : Colors.border,
                }}
              >
                <Text
                  className="text-[11px] font-bold"
                  style={{ color: categoryFilter === 'all' ? '#fff' : Colors.navy }}
                >
                  All
                </Text>
              </Pressable>
              {summary.topCategories.map((cat) => {
                const active = categoryFilter === cat.label;
                return (
                  <Pressable
                    key={cat.label}
                    onPress={() => {
                      void hapticSelection();
                      setCategoryFilter(cat.label);
                    }}
                    className="rounded-full px-3 py-1.5"
                    style={{
                      backgroundColor: active ? cat.style.fg : cat.style.bg,
                      borderWidth: 1,
                      borderColor: cat.style.fg,
                    }}
                  >
                    <Text
                      className="text-[11px] font-bold"
                      style={{ color: active ? '#fff' : cat.style.fg }}
                    >
                      {cat.label} · {formatMoney(cat.amount, true)}
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>

          {filteredRows.length === 0 ? (
            <Text className="text-center text-body text-muted">No rows in this category.</Text>
          ) : (
            filteredRows.map((row) => <SalesRow key={row.id} row={row} />)
          )}
        </>
      )}
    </ScrollView>
  );
}
