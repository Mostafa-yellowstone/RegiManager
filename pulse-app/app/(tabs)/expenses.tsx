import { Text, View } from 'react-native';

export default function ExpensesScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-cream px-8">
      <Text className="text-title text-navy">Expense tracking</Text>
      <Text className="mt-2 text-center text-body text-muted">
        Review spend and P&L breakdown. Owners do not add expenses in Pulse.
      </Text>
    </View>
  );
}
