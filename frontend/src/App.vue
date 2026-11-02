<template>
  <n-config-provider :theme="darkTheme">
    <div v-if="embedded" class="embedded-pane"><router-view /></div>
    <WorkspaceNavigation v-else>
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </WorkspaceNavigation>
  </n-config-provider>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { NConfigProvider, darkTheme } from 'naive-ui';
import WorkspaceNavigation from '@/components/Workspace/WorkspaceNavigation.vue';
import { wsService } from './utils/websocketService';
import { IS_SECOND_PANE } from './utils/chartPane';

export default defineComponent({
  name: 'App',

  components: {
    NConfigProvider,
    WorkspaceNavigation,
  },

  data() {
    return {
      darkTheme,
      embedded: IS_SECOND_PANE,
    };
  },

  beforeUnmount() {
    wsService.close();
  },
});
</script>

<style>
.embedded-pane {
  position: fixed;
  inset: 0;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  color-scheme: dark;
}
</style>
