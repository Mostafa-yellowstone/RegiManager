import { Tabs } from 'expo-router';
import { Text, type ColorValue } from 'react-native';

import { hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

function TabLabel({ label, color }: { label: string; color: ColorValue }) {
  return <Text style={{ color, fontSize: 11, fontWeight: '700' }}>{label}</Text>;
}

export default function TabLayout() {
  return (
    <Tabs
      screenListeners={{
        tabPress: () => {
          void hapticSelection();
        },
      }}
      screenOptions={{
        tabBarActiveTintColor: Colors.navy,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
          height: 64,
          paddingBottom: 10,
          paddingTop: 8,
        },
        headerStyle: { backgroundColor: Colors.navy },
        headerTintColor: Colors.white,
        headerTitleStyle: { fontWeight: '800', letterSpacing: 0.2 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Pulse',
          tabBarLabel: ({ color }) => <TabLabel label="Pulse" color={color} />,
        }}
      />
      <Tabs.Screen
        name="sales"
        options={{
          title: 'Sales',
          tabBarLabel: ({ color }) => <TabLabel label="Sales" color={color} />,
        }}
      />
      <Tabs.Screen
        name="staff"
        options={{
          title: 'Staff',
          tabBarLabel: ({ color }) => <TabLabel label="Staff" color={color} />,
        }}
      />
      <Tabs.Screen
        name="expenses"
        options={{
          title: 'Expenses',
          tabBarLabel: ({ color }) => <TabLabel label="Expenses" color={color} />,
        }}
      />
    </Tabs>
  );
}
