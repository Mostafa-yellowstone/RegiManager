import { SymbolView } from 'expo-symbols';
import { Tabs } from 'expo-router';

import { Colors } from '@/constants/theme';

function TabIcon({
  ios,
  android,
  color,
}: {
  ios: string;
  android: string;
  color: string;
}) {
  return (
    <SymbolView
      name={{ ios: ios as any, android: android as any, web: android as any }}
      tintColor={color}
      size={24}
    />
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors.primaryMid,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontWeight: '600', fontSize: 11 },
        headerStyle: { backgroundColor: Colors.navy },
        headerTintColor: Colors.white,
        headerTitleStyle: { fontWeight: '800', fontSize: 17 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Account Center',
          tabBarLabel: 'Home',
          tabBarIcon: ({ color }) => <TabIcon ios="house.fill" android="home" color={color} />,
        }}
      />
      <Tabs.Screen
        name="policies"
        options={{
          title: 'Policies',
          tabBarIcon: ({ color }) => <TabIcon ios="doc.text" android="description" color={color} />,
        }}
      />
      <Tabs.Screen
        name="vehicles"
        options={{
          title: 'Vehicles',
          tabBarIcon: ({ color }) => <TabIcon ios="car.fill" android="directions_car" color={color} />,
        }}
      />
      <Tabs.Screen
        name="receipts"
        options={{
          title: 'Receipts',
          tabBarIcon: ({ color }) => <TabIcon ios="receipt" android="receipt" color={color} />,
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: 'Messages',
          tabBarIcon: ({ color }) => <TabIcon ios="bubble.left.and.bubble.right.fill" android="chat" color={color} />,
        }}
      />
      <Tabs.Screen name="id-cards" options={{ title: 'ID Cards', href: null }} />
      <Tabs.Screen name="documents" options={{ title: 'Document Vault', href: null }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile & Settings', href: null }} />
    </Tabs>
  );
}
