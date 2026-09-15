import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetFlatList,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { forwardRef, useCallback, useMemo } from 'react';
import { Pressable, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { formatMoney } from '@/lib/format';
import { hapticSelection, hapticSuccess } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
import type { SpaceIdOrAll } from '@/types/models';

export type SpaceOption = {
  id: SpaceIdOrAll;
  name: string;
  location?: string;
  revenue?: number;
};

type Props = {
  options: SpaceOption[];
  selectedId: SpaceIdOrAll;
  onSelect: (id: SpaceIdOrAll) => void;
};

export const SpaceSwitcherSheet = forwardRef<BottomSheet, Props>(
  function SpaceSwitcherSheet({ options, selectedId, onSelect }, ref) {
    const snapPoints = useMemo(() => ['42%', '68%'], []);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.35} />
      ),
      [],
    );

    return (
      <BottomSheet
        ref={ref}
        index={-1}
        snapPoints={snapPoints}
        enablePanDownToClose
        backdropComponent={renderBackdrop}
        backgroundStyle={{ backgroundColor: '#FFFFFF' }}
        handleIndicatorStyle={{ backgroundColor: '#CBD5E1', width: 40 }}
      >
        <View className="px-4 pb-2">
          <Text className="text-title text-navy">Switch space</Text>
          <Text className="mt-1 text-caption text-muted">
            Filter by product space. Amounts show profit for the selected date range.
          </Text>
        </View>
        <BottomSheetFlatList
          data={options}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 32 }}
          renderItem={({ item }) => {
            const active = item.id === selectedId;
            return (
              <Pressable
                onPress={async () => {
                  await hapticSelection();
                  onSelect(item.id);
                  await hapticSuccess();
                }}
                className="mb-2 rounded-2xl border px-4 py-3"
                style={{
                  borderColor: active ? Colors.teal : Colors.border,
                  backgroundColor: active ? Colors.tealSoft : Colors.white,
                }}
                android_ripple={{ color: 'rgba(13,148,136,0.08)' }}
              >
                <View className="flex-row items-center justify-between">
                  <View className="flex-1 pr-3">
                    <Text className="text-body font-bold text-navy">{item.name}</Text>
                    {item.location ? (
                      <Text className="mt-0.5 text-caption text-muted">{item.location}</Text>
                    ) : null}
                  </View>
                  {item.revenue != null ? (
                    <Text className="text-caption font-bold text-teal">
                      {formatMoney(item.revenue, true)}
                    </Text>
                  ) : null}
                </View>
              </Pressable>
            );
          }}
        />
      </BottomSheet>
    );
  },
);

type TriggerProps = {
  label: string;
  onPress: () => void;
};

export function SpaceSwitcherTrigger({ label, onPress }: TriggerProps) {
  return (
    <Pressable onPress={onPress} className="items-end">
      <View
        className="flex-row items-center rounded-full bg-white px-3 py-2"
        style={{
          borderWidth: 1,
          borderColor: Colors.border,
          shadowColor: '#0F3D4C',
          shadowOpacity: 0.06,
          shadowRadius: 8,
          shadowOffset: { width: 0, height: 2 },
          elevation: 2,
        }}
      >
        <Svg width={14} height={14} viewBox="0 0 24 24" style={{ marginRight: 6 }}>
          <Path
            d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"
            fill={Colors.teal}
          />
        </Svg>
        <Text className="text-caption font-bold text-navy" numberOfLines={1}>
          {label}
        </Text>
      </View>
      <Text className="mt-1 text-[11px] font-bold" style={{ color: Colors.blue }}>
        change
      </Text>
    </Pressable>
  );
}
