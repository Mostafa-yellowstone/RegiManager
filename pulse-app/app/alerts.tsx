import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { fetchOwnerNotifications, markOwnerNotificationRead } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';

export default function AlertsScreen() {
  const { selectedOrg } = useAuth();
  const queryClient = useQueryClient();
  const alerts = useQuery({
    queryKey: ['pulse-alerts', selectedOrg?.id],
    queryFn: () => fetchOwnerNotifications(),
    enabled: Boolean(selectedOrg?.id),
  });

  const markRead = useMutation({
    mutationFn: (id: number) => markOwnerNotificationRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pulse-alerts'] });
    },
  });

  const rows = alerts.data?.notifications || [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: Colors.cream }}
      contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 40 }}
      refreshControl={
        <RefreshControl
          refreshing={alerts.isFetching && !alerts.isLoading}
          onRefresh={() => {
            void hapticLight();
            void alerts.refetch();
          }}
          tintColor={Colors.teal}
        />
      }
    >
      {alerts.isError ? (
        <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
          {(alerts.error as Error)?.message || 'Could not load alerts'}
        </Text>
      ) : null}
      {alerts.isLoading ? (
        <>
          <SkeletonBlock height={72} />
          <SkeletonBlock height={72} />
        </>
      ) : rows.length === 0 ? (
        <Text style={{ marginTop: 24, textAlign: 'center', fontFamily: Fonts.medium, color: Colors.muted }}>
          No alerts.
        </Text>
      ) : (
        rows.map((note: any) => (
          <Pressable
            key={note.id}
            onPress={() => {
              void hapticSelection();
              if (!note.is_read) markRead.mutate(Number(note.id));
            }}
            style={{
              backgroundColor: note.is_read ? Colors.white : Colors.tealSoft,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: Colors.border,
              padding: 14,
              gap: 4,
            }}
          >
            <Text style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}>{note.title || 'Alert'}</Text>
            {note.message ? (
              <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted, lineHeight: 18 }}>
                {note.message}
              </Text>
            ) : null}
            <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
              {[note.client_name, note.created_at ? String(note.created_at).slice(0, 16).replace('T', ' ') : '']
                .filter(Boolean)
                .join(' · ')}
            </Text>
          </Pressable>
        ))
      )}
    </ScrollView>
  );
}
