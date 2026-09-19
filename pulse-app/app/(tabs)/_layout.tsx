import { useQuery } from '@tanstack/react-query';
import { Tabs, useRouter } from 'expo-router';
import { Pressable, Text } from 'react-native';

import { PulseTabBar } from '@/components/pulse/PulseTabBar';
import { orgHasInsuranceAccess } from '@/data/repositories/insuranceRepository';
import { useAuth } from '@/lib/auth';
import { hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';

export default function TabLayout() {
  const router = useRouter();
  const { logout, selectedOrg } = useAuth();

  const insuranceAccessQuery = useQuery({
    queryKey: ['pulse-has-insurance', selectedOrg?.id],
    queryFn: () => orgHasInsuranceAccess(),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 60_000,
  });

  const hasInsurance = Boolean(insuranceAccessQuery.data);

  return (
    <Tabs
      tabBar={(props) => <PulseTabBar {...props} />}
      screenListeners={{
        tabPress: () => {
          void hapticSelection();
        },
      }}
      screenOptions={{
        headerStyle: { backgroundColor: Colors.white },
        headerShadowVisible: false,
        headerTintColor: Colors.navy,
        headerTitleStyle: { fontFamily: Fonts.bold, fontWeight: '800', color: Colors.teal },
        headerRight: () => (
          <Pressable
            onPress={() => {
              void (async () => {
                await hapticSelection();
                await logout();
                router.replace('/login');
              })();
            }}
            style={{ marginRight: 14 }}
          >
            <Text style={{ color: Colors.teal, fontFamily: Fonts.bold, fontSize: 13 }}>Sign out</Text>
          </Pressable>
        ),
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Pulse', headerShown: false }} />
      <Tabs.Screen name="sales" options={{ title: 'Sales' }} />
      <Tabs.Screen
        name="insurance"
        options={{
          title: 'Insurance',
          headerShown: false,
          href: hasInsurance ? ('/(tabs)/insurance' as any) : null,
        }}
      />
      <Tabs.Screen name="staff" options={{ title: 'Staff' }} />
      <Tabs.Screen name="expenses" options={{ title: 'Expenses' }} />
    </Tabs>
  );
}
