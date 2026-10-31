import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useMemo, useState, type ReactNode } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listDeskJobs, jobStatusLabel, type DeskJob } from '@/data/repositories/workRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useDeskStore, type WorkKind, type WorkStatus } from '@/stores/deskStore';

const KIND_CHIPS: Array<{ id: WorkKind; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'desk', label: 'Desk' },
  { id: 'insurance', label: 'Insurance' },
  { id: 'motorclub', label: 'Motor Club' },
  { id: 'tlc', label: 'TLC' },
];

const STATUS_CHIPS: Array<{ id: WorkStatus; label: string }> = [
  { id: 'all', label: 'Any status' },
  { id: 'waiting', label: 'Waiting' },
  { id: 'done', label: 'Done' },
  { id: 'failed', label: 'Needs you' },
  { id: 'refund', label: 'Refunded' },
];

function matchesStatus(job: DeskJob, status: WorkStatus) {
  if (status === 'all') return true;
  const label = jobStatusLabel(job.status);
  if (status === 'waiting') return label === 'Waiting';
  if (status === 'done') return label === 'Done';
  if (status === 'failed') return label === 'Needs you';
  if (status === 'refund') return label === 'Refunded';
  return true;
}

export default function WorkScreen() {
  const router = useRouter();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const query = useDeskStore((s) => s.query);
  const kind = useDeskStore((s) => s.kind);
  const status = useDeskStore((s) => s.status);
  const person = useDeskStore((s) => s.person);
  const setKind = useDeskStore((s) => s.setKind);
  const setStatus = useDeskStore((s) => s.setStatus);
  const setPerson = useDeskStore((s) => s.setPerson);

  const jobsQuery = useQuery({
    queryKey: ['pulse-work', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => listDeskJobs(),
    enabled: Boolean(selectedOrg?.id),
  });

  const people = useMemo(() => {
    const names = new Set<string>();
    for (const job of jobsQuery.data ?? []) {
      if (job.person) names.add(job.person);
    }
    return [...names].sort((a, b) => a.localeCompare(b)).slice(0, 8);
  }, [jobsQuery.data]);

  const visibleKinds = useMemo(() => {
    const present = new Set((jobsQuery.data ?? []).map((job) => job.kind));
    return KIND_CHIPS.filter((chip) => chip.id === 'all' || chip.id === 'desk' || present.has(chip.id));
  }, [jobsQuery.data]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (jobsQuery.data ?? []).filter((job) => {
      if (kind !== 'all' && job.kind !== kind) return false;
      if (person && job.person !== person) return false;
      if (!matchesStatus(job, status)) return false;
      if (!needle) return true;
      const hay = [job.title, job.customer, job.person, job.detail, job.kindLabel, jobStatusLabel(job.status)]
        .join(' ')
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [jobsQuery.data, kind, person, query, status]);

  const kindLabel = KIND_CHIPS.find((chip) => chip.id === kind)?.label || 'All';
  const statusLabel = STATUS_CHIPS.find((chip) => chip.id === status)?.label || 'Any status';
  const filterLine = [
    kind === 'all' ? '' : kindLabel,
    status === 'all' ? '' : statusLabel,
    person ? person.split(' ')[0] : '',
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 120, gap: 12 }}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={jobsQuery.isFetching && !jobsQuery.isLoading}
            onRefresh={() => {
              void hapticLight();
              void jobsQuery.refetch();
            }}
            tintColor={Colors.tealDeep}
          />
        }
      >
        <ConnectedDateRangeSelector />
        <Pressable
          onPress={() => {
            void hapticSelection();
            setFiltersOpen((open) => !open);
          }}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: Colors.white,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: Colors.border,
            paddingHorizontal: 14,
            paddingVertical: 12,
          }}
        >
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={{ fontFamily: Fonts.bold, fontSize: 14, color: Colors.navy }}>Filters</Text>
            <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }} numberOfLines={1}>
              {filterLine || 'All work'}
            </Text>
          </View>
          <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.tealDeep }}>
            {filtersOpen ? 'Hide' : 'Show'}
          </Text>
        </Pressable>
        {filtersOpen ? (
          <Animated.View entering={FadeIn.duration(180)} style={{ gap: 12 }}>
            <FilterGroup title="Kind">
              <ChipRow
                chips={visibleKinds}
                active={kind}
                onPress={(id) => {
                  void hapticSelection();
                  setKind(id);
                }}
              />
            </FilterGroup>
            <FilterGroup title="Status">
              <ChipRow
                chips={STATUS_CHIPS}
                active={status}
                onPress={(id) => {
                  void hapticSelection();
                  setStatus(id);
                }}
              />
            </FilterGroup>
            {people.length > 0 ? (
              <FilterGroup title="Person">
                <ChipRow
                  chips={[
                    { id: '', label: 'Anyone' },
                    ...people.map((name) => ({ id: name, label: name.split(' ')[0] || name })),
                  ]}
                  active={person}
                  onPress={(id) => {
                    void hapticSelection();
                    setPerson(id);
                  }}
                />
              </FilterGroup>
            ) : null}
          </Animated.View>
        ) : null}

        {jobsQuery.isError ? (
          <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
            {(jobsQuery.error as Error)?.message || 'Could not load work'}
          </Text>
        ) : null}

        {jobsQuery.isLoading ? (
          <>
            <SkeletonBlock height={84} />
            <SkeletonBlock height={84} />
            <SkeletonBlock height={84} />
          </>
        ) : rows.length === 0 ? (
          <Text style={{ textAlign: 'center', marginTop: 24, fontFamily: Fonts.medium, color: Colors.muted }}>
            Nothing matches.
          </Text>
        ) : (
          rows.map((job) => (
            <Pressable
              key={job.id}
              onPress={() => {
                void hapticSelection();
                router.push({
                  pathname: '/job/[id]' as any,
                  params: {
                    id: job.id,
                    title: job.title,
                    customer: job.customer,
                    person: job.person,
                    status: job.status,
                    kind: job.kindLabel,
                    amount: String(job.amount),
                    date: job.date,
                    detail: job.detail,
                  },
                });
              }}
              style={{
                backgroundColor: Colors.white,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: Colors.border,
                padding: 14,
                gap: 6,
              }}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.teal }}>{job.kindLabel}</Text>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.muted }}>
                  {jobStatusLabel(job.status)}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }} numberOfLines={2}>
                    {job.title}
                  </Text>
                  {job.customer ? (
                    <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }} numberOfLines={2}>
                      {job.customer}
                    </Text>
                  ) : null}
                  <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                    {[job.person, job.date].filter(Boolean).join(' · ')}
                  </Text>
                </View>
                {job.amount ? (
                  <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }}>
                    {formatMoney(job.amount)}
                  </Text>
                ) : null}
              </View>
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.muted }}>{title}</Text>
      {children}
    </View>
  );
}

function ChipRow<T extends string>({
  chips,
  active,
  onPress,
}: {
  chips: Array<{ id: T; label: string }>;
  active: T;
  onPress: (id: T) => void;
}) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {chips.map((chip) => {
        const on = chip.id === active;
        return (
          <Pressable
            key={chip.id || 'all'}
            onPress={() => onPress(chip.id)}
            style={{
              borderRadius: 999,
              paddingHorizontal: 12,
              paddingVertical: 7,
              backgroundColor: on ? Colors.navy : Colors.white,
              borderWidth: 1,
              borderColor: on ? Colors.navy : Colors.border,
            }}
          >
            <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: on ? Colors.white : Colors.navy }}>
              {chip.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
