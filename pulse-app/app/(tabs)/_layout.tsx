import { Tabs, usePathname } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DeskHeader } from '@/components/pulse/DeskHeader';
import { PulseRequestBar } from '@/components/pulse/PulseRequestBar';
import { PulseTabBar } from '@/components/pulse/PulseTabBar';
import { hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const pathname = usePathname();
  const onHome =
    !pathname.includes('sales') &&
    !pathname.includes('insurance') &&
    !pathname.includes('staff') &&
    !pathname.includes('expenses');

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream, paddingTop: insets.top }}>
      {onHome ? null : <DeskHeader />}
      <PulseRequestBar />
      <View style={{ flex: 1 }}>
        <Tabs
          tabBar={(props) => <PulseTabBar {...props} />}
          screenListeners={{
            tabPress: () => {
              void hapticSelection();
            },
          }}
          screenOptions={{
            headerShown: false,
            sceneStyle: { backgroundColor: Colors.cream },
          }}
        >
          <Tabs.Screen name="index" options={{ title: 'Pulse' }} />
          <Tabs.Screen name="sales" options={{ title: 'Sales' }} />
          <Tabs.Screen name="insurance" options={{ title: 'Insurance' }} />
          <Tabs.Screen name="staff" options={{ title: 'Staff' }} />
          <Tabs.Screen name="expenses" options={{ title: 'Expenses' }} />
        </Tabs>
      </View>
    </View>
  );
}
