<script setup lang="ts">
import BaseGroupedSelect from '@/components/Common/BaseGroupedSelect.vue';
import { useCurrentTimeframeStore } from '@/stores/currentTimeframeStore';
import { groupTimeframeOptions, TIMEFRAME_OPTIONS } from '@/utils/timeframes';
import { isTimeframeCode } from '@/types/contracts';

const props = defineProps<{
  /** When set, show this timeframe and emit the choice instead of changing this chart. */
  remoteValue?: string;
}>();
const emit = defineEmits<{ 'remote-select': [value: string] }>();

const currentTimeframeStore = useCurrentTimeframeStore();
const groups = groupTimeframeOptions(TIMEFRAME_OPTIONS);

function selectTimeframe(value: string): void {
  if (props.remoteValue !== undefined) {
    emit('remote-select', value);
    return;
  }
  if (isTimeframeCode(value)) {
    currentTimeframeStore.setCurrentTimeframe({ label: value, value });
  }
}
</script>

<template>
  <BaseGroupedSelect
    :value="remoteValue ?? currentTimeframeStore.value"
    label="Timeframe"
    :groups="groups"
    trigger-width="80px"
    @update:value="selectTimeframe"
  />
</template>
