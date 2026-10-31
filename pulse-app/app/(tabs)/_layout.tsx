import { Tabs } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DeskHeader } from '@/components/pulse/DeskHeader';
import { PulseRequestBar } from '@/components/pulse/PulseRequestBar';
import { PulseTabBar } from '@/components/pulse/PulseTabBar';
import { hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

export default function TabLayout() {
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream, paddingTop: insets.top }}>
      <DeskHeader />
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
          <Tabs.Screen name="index" options={{ title: 'Today' }} />
          <Tabs.Screen name="sales" options={{ title: 'Work' }} />
          <Tabs.Screen name="expenses" options={{ title: 'Money' }} />
          <Tabs.Screen name="staff" options={{ title: 'Team' }} />
          <Tabs.Screen name="insurance" options={{ title: 'Insurance', href: null }} />
        </Tabs>
      </View>
    </View>
  );
}
