import { Platform } from 'react-native';
import DateTimePicker, {
  type DateTimePickerEvent,
} from '@react-native-community/datetimepicker';
import { useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View } from 'react-native';

import { formatRangeChipLabel, isoLocal, parseIsoLocal } from '@/lib/dateRange';
import { hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import type { DateRangePreset } from '@/types/models';

const OPTIONS: Array<{ id: DateRangePreset; label: string }> = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'week', label: 'This Week' },
  { id: 'month', label: 'This Month' },
  { id: 'ytd', label: 'YTD' },
];

type Props = {
  value: DateRangePreset;
  customStart?: string | null;
  customEnd?: string | null;
  onChange: (preset: DateRangePreset) => void;
  onCustomRange: (start: string, end: string) => void;
};

export function DateRangeSelector({
  value,
  customStart,
  customEnd,
  onChange,
  onCustomRange,
}: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(() => customStart || isoLocal(new Date()));
  const [draftEnd, setDraftEnd] = useState(() => customEnd || isoLocal(new Date()));
  const [picking, setPicking] = useState<'start' | 'end' | null>(null);

  const customActive = value === 'custom';
  const customLabel = formatRangeChipLabel(customStart ?? null, customEnd ?? null);

  function openCustom() {
    const today = isoLocal(new Date());
    setDraftStart(customStart || today);
    setDraftEnd(customEnd || today);
    setSheetOpen(true);
  }

  function applyCustom() {
    const from = draftStart <= draftEnd ? draftStart : draftEnd;
    const to = draftStart <= draftEnd ? draftEnd : draftStart;
    onCustomRange(from, to);
    setSheetOpen(false);
    setPicking(null);
  }

  function onPickerChange(event: DateTimePickerEvent, date?: Date) {
    if (Platform.OS === 'android') {
      setPicking(null);
      if (event.type !== 'set' || !date) return;
    }
    if (!date || !picking) return;
    const next = isoLocal(date);
    if (picking === 'start') setDraftStart(next);
    else setDraftEnd(next);
  }

  return (
    <>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }}>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {OPTIONS.map((opt) => {
            const active = opt.id === value;
            return (
              <Pressable
                key={opt.id}
                onPress={async () => {
                  await hapticSelection();
                  onChange(opt.id);
                }}
                style={{
                  borderRadius: 999,
                  paddingHorizontal: 14,
                  paddingVertical: 9,
                  backgroundColor: active ? Colors.teal : Colors.white,
                  borderWidth: 1,
                  borderColor: active ? Colors.teal : Colors.border,
                }}
                android_ripple={{ color: 'rgba(13,148,136,0.12)' }}
              >
                <Text
                  style={{
                    fontFamily: Fonts.bold,
                    fontSize: 12,
                    color: active ? Colors.white : Colors.navy,
                  }}
                >
                  {opt.label}
                </Text>
              </Pressable>
            );
          })}
          <Pressable
            onPress={async () => {
              await hapticSelection();
              openCustom();
            }}
            style={{
              borderRadius: 999,
              paddingHorizontal: 14,
              paddingVertical: 9,
              backgroundColor: customActive ? Colors.teal : Colors.white,
              borderWidth: 1,
              borderColor: customActive ? Colors.teal : Colors.border,
            }}
            android_ripple={{ color: 'rgba(13,148,136,0.12)' }}
          >
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 12,
                color: customActive ? Colors.white : Colors.navy,
              }}
            >
              {customActive ? customLabel : 'Custom'}
            </Text>
          </Pressable>
        </View>
      </ScrollView>

      <Modal visible={sheetOpen} transparent animationType="fade" onRequestClose={() => setSheetOpen(false)}>
        <Pressable
          style={{ flex: 1, backgroundColor: 'rgba(11,61,58,0.45)', justifyContent: 'flex-end' }}
          onPress={() => setSheetOpen(false)}
        >
          <Pressable
            onPress={() => undefined}
            style={{
              backgroundColor: Colors.white,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: 20,
              gap: 14,
            }}
          >
            <Text style={{ fontFamily: Fonts.bold, fontSize: 18, color: Colors.navy }}>
              Custom range
            </Text>
            <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
              Pick a from and to date to load that exact window across Pulse.
            </Text>

            <View style={{ flexDirection: 'row', gap: 10 }}>
              <Pressable
                onPress={() => setPicking('start')}
                style={{
                  flex: 1,
                  borderRadius: 14,
                  borderWidth: 1,
                  borderColor: picking === 'start' ? Colors.teal : Colors.border,
                  backgroundColor: Colors.cream,
                  padding: 12,
                }}
              >
                <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.tealDeep }}>
                  FROM
                </Text>
                <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 16, color: Colors.navy }}>
                  {draftStart}
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setPicking('end')}
                style={{
                  flex: 1,
                  borderRadius: 14,
                  borderWidth: 1,
                  borderColor: picking === 'end' ? Colors.teal : Colors.border,
                  backgroundColor: Colors.cream,
                  padding: 12,
                }}
              >
                <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.tealDeep }}>
                  TO
                </Text>
                <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 16, color: Colors.navy }}>
                  {draftEnd}
                </Text>
              </Pressable>
            </View>

            {picking ? (
              <DateTimePicker
                value={parseIsoLocal(picking === 'start' ? draftStart : draftEnd)}
                mode="date"
                display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                onChange={onPickerChange}
                maximumDate={new Date()}
              />
            ) : null}

            <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
              <Pressable
                onPress={() => {
                  setSheetOpen(false);
                  setPicking(null);
                }}
                style={{
                  flex: 1,
                  alignItems: 'center',
                  borderRadius: 12,
                  paddingVertical: 12,
                  borderWidth: 1,
                  borderColor: Colors.border,
                }}
              >
                <Text style={{ fontFamily: Fonts.bold, fontSize: 14, color: Colors.navy }}>Cancel</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  void hapticSelection();
                  applyCustom();
                }}
                style={{
                  flex: 1,
                  alignItems: 'center',
                  borderRadius: 12,
                  paddingVertical: 12,
                  backgroundColor: Colors.teal,
                }}
              >
                <Text style={{ fontFamily: Fonts.bold, fontSize: 14, color: Colors.white }}>Apply</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}
