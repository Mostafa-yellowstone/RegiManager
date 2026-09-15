import { Link, Stack } from 'expo-router';
import { Text, View } from 'react-native';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Oops!' }} />
      <View className="flex-1 items-center justify-center bg-cream px-6">
        <Text className="text-title text-navy">This screen does not exist.</Text>
        <Link href="/" className="mt-4">
          <Text className="font-bold text-navy">Go to Pulse</Text>
        </Link>
      </View>
    </>
  );
}
