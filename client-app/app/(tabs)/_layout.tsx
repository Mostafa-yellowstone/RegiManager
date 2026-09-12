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
        tabBarActiveTintColor: Colors.teal,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
        },
        headerStyle: { backgroundColor: Colors.navy },
        headerTintColor: Colors.white,
        headerTitleStyle: { fontWeight: '700' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Wallet',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="wallet.pass" android="account_balance_wallet" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="policies"
        options={{
          title: 'Policies',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="doc.text" android="description" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="id-cards"
        options={{
          title: 'ID Cards',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="person.crop.rectangle" android="badge" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="documents"
        options={{
          title: 'Docs',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="folder" android="folder" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="person.circle" android="person" color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
