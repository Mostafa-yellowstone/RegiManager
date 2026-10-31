import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, Text, TextInput, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

import { fetchOwnerNotifications } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import { useDeskStore } from '@/stores/deskStore';
import { useSpaceStore } from '@/stores/spaceStore';

function GearIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"
        stroke={Colors.tealDeep}
        strokeWidth={1.7}
      />
      <Circle cx="12" cy="12" r="9" stroke={Colors.tealDeep} strokeWidth={1.5} fill="none" />
    </Svg>
  );
}

function BellIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9Z"
        stroke={Colors.tealDeep}
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <Path d="M10 20a2 2 0 0 0 4 0" stroke={Colors.tealDeep} strokeWidth={1.7} strokeLinecap="round" />
    </Svg>
  );
}

export function DeskHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { selectedOrg, organizations, selectOrganization } = useAuth();
  const query = useDeskStore((s) => s.query);
  const setQuery = useDeskStore((s) => s.setQuery);
  const setSelectedSpaceId = useSpaceStore((s) => s.setSelectedSpaceId);
  const [focused, setFocused] = useState(false);

  const alertsQuery = useQuery({
    queryKey: ['pulse-alerts', selectedOrg?.id],
    queryFn: () => fetchOwnerNotifications(),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 30_000,
  });
  const unread = Number(alertsQuery.data?.unread_count || 0);

  const office = selectedOrg
    ? selectedOrg.city
      ? `${selectedOrg.name} · ${selectedOrg.city}`
      : selectedOrg.name
    : 'Office';

  function onSearch(text: string) {
    setQuery(text);
    const onWork = pathname.includes('sales');
    if (text.trim() && !onWork) {
      router.navigate('/(tabs)/sales');
    }
  }

  async function onPickOrg() {
    if (organizations.length < 2) return;
    await hapticSelection();
    Alert.alert('Switch office', undefined, [
      ...organizations.map((org) => ({
        text: org.city ? `${org.name} · ${org.city}` : org.name,
        onPress: () => {
          void (async () => {
            await selectOrganization(org.id);
            setSelectedSpaceId('all');
            await queryClient.invalidateQueries();
          })();
        },
      })),
      { text: 'Cancel', style: 'cancel' },
    ]);
  }

  return (
    <View style={{ paddingHorizontal: 16, paddingBottom: 12, gap: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Pressable style={{ flex: 1 }} onPress={() => void onPickOrg()}>
          <Text
            numberOfLines={1}
            style={{ fontFamily: Fonts.extrabold, fontSize: 22, color: Colors.navy, letterSpacing: -0.4 }}
          >
            {office}
            {organizations.length > 1 ? ' ▾' : ''}
          </Text>
        </Pressable>
        <Pressable
          accessibilityLabel="Alerts"
          onPress={() => {
            void hapticLight();
            router.push('/alerts' as any);
          }}
          style={iconButton}
        >
          <BellIcon />
          {unread > 0 ? (
            <View
              style={{
                position: 'absolute',
                top: 6,
                right: 6,
                minWidth: 16,
                height: 16,
                borderRadius: 8,
                paddingHorizontal: 4,
                backgroundColor: Colors.orange,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: Colors.white, fontFamily: Fonts.bold, fontSize: 9 }}>
                {unread > 9 ? '9+' : unread}
              </Text>
            </View>
          ) : null}
        </Pressable>
        <Pressable
          accessibilityLabel="Settings"
          onPress={() => {
            void hapticLight();
            router.push('/settings');
          }}
          style={iconButton}
        >
          <GearIcon />
        </Pressable>
      </View>
      <TextInput
        value={query}
        onChangeText={onSearch}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="Search jobs, customers, people"
        placeholderTextColor={Colors.mutedLight}
        autoCapitalize="none"
        autoCorrect={false}
        clearButtonMode="while-editing"
        returnKeyType="search"
        style={{
          backgroundColor: Colors.white,
          borderWidth: 1,
          borderColor: focused ? Colors.teal : Colors.border,
          borderRadius: 14,
          paddingHorizontal: 14,
          paddingVertical: 12,
          fontFamily: Fonts.medium,
          fontSize: 15,
          color: Colors.navy,
        }}
      />
    </View>
  );
}

const iconButton = {
  width: 40,
  height: 40,
  borderRadius: 12,
  alignItems: 'center' as const,
  justifyContent: 'center' as const,
  backgroundColor: Colors.white,
  borderWidth: 1,
  borderColor: Colors.border,
};
