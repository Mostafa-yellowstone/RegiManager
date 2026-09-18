import {
  BottomSheetBackdrop,
  BottomSheetFlatList,
  BottomSheetModal,
  type BottomSheetBackdropProps,
  type BottomSheetModal as BottomSheetModalType,
} from '@gorhom/bottom-sheet';
import { forwardRef, useCallback, useMemo } from 'react';
import { Text, View } from 'react-native';
import { TouchableOpacity } from 'react-native-gesture-handler';
import Svg, { Path } from 'react-native-svg';

import { formatMoney } from '@/lib/format';
import { hapticSelection, hapticSuccess } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
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

export const SpaceSwitcherSheet = forwardRef<BottomSheetModalType, Props>(
  function SpaceSwitcherSheet({ options, selectedId, onSelect }, ref) {
    const snapPoints = useMemo(() => ['42%', '68%'], []);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.35} />
      ),
      [],
    );

    return (
      <BottomSheetModal
        ref={ref}
        snapPoints={snapPoints}
        enablePanDownToClose
        backdropComponent={renderBackdrop}
        backgroundStyle={{ backgroundColor: '#FFFFFF' }}
        handleIndicatorStyle={{ backgroundColor: '#CBD5E1', width: 40 }}
      >
        <View className="px-4 pb-2">
          <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Switch space</Text>
          <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            Filter metrics by product space for this date range.
          </Text>
        </View>
        <BottomSheetFlatList
          data={options}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 32 }}
          renderItem={({ item }) => {
            const active = item.id === selectedId;
            return (
              <TouchableOpacity
                activeOpacity={0.7}
                onPress={() => {
                  void (async () => {
                    await hapticSelection();
                    onSelect(item.id);
                    await hapticSuccess();
                  })();
                }}
                style={{
                  marginBottom: 8,
                  borderRadius: 16,
                  borderWidth: 1,
                  paddingHorizontal: 16,
                  paddingVertical: 12,
                  borderColor: active ? Colors.teal : Colors.border,
                  backgroundColor: active ? Colors.tealSoft : Colors.white,
                }}
              >
                <View className="flex-row items-center justify-between">
                  <View className="flex-1 pr-3">
                    <Text style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}>
                      {item.name}
                    </Text>
                    {item.location ? (
                      <Text
                        style={{
                          marginTop: 2,
                          fontFamily: Fonts.medium,
                          fontSize: 12,
                          color: Colors.muted,
                        }}
                      >
                        {item.location}
                      </Text>
                    ) : null}
                  </View>
                  {item.revenue != null ? (
                    <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.teal }}>
                      {formatMoney(item.revenue, true)}
                    </Text>
                  ) : null}
                </View>
              </TouchableOpacity>
            );
          }}
        />
      </BottomSheetModal>
    );
  },
);

type TriggerProps = {
  label: string;
  onPress: () => void;
};

export function SpaceSwitcherTrigger({ label, onPress }: TriggerProps) {
  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7}>
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          borderRadius: 999,
          backgroundColor: Colors.white,
          paddingHorizontal: 12,
          paddingVertical: 8,
          borderWidth: 1,
          borderColor: Colors.border,
        }}
      >
        <Svg width={14} height={14} viewBox="0 0 24 24" style={{ marginRight: 6 }}>
          <Path
            d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"
            fill={Colors.teal}
          />
        </Svg>
        <Text
          numberOfLines={1}
          style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.navy, maxWidth: 120 }}
        >
          {label}
        </Text>
        <Text style={{ marginLeft: 4, fontFamily: Fonts.bold, fontSize: 10, color: Colors.teal }}>
          ▾
        </Text>
      </View>
    </TouchableOpacity>
  );
}
