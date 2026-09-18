import { Tabs, useRouter } from 'expo-router';
import { Pressable, Text } from 'react-native';

import { PulseTabBar } from '@/components/pulse/PulseTabBar';
import { useAuth } from '@/lib/auth';
import { hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

export default function TabLayout() {
  const router = useRouter();
  const { logout } = useAuth();

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
        headerTitleStyle: { fontWeight: '800', color: Colors.teal },
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
            <Text style={{ color: Colors.teal, fontWeight: '700', fontSize: 13 }}>Sign out</Text>
          </Pressable>
        ),
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Pulse' }} />
      <Tabs.Screen name="sales" options={{ title: 'Sales' }} />
      <Tabs.Screen name="staff" options={{ title: 'Staff' }} />
      <Tabs.Screen name="expenses" options={{ title: 'Expenses' }} />
    </Tabs>
  );
}
