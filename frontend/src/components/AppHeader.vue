<script setup lang="ts">
import {
  PhBookOpen,
  PhCaretDown,
  PhClockCounterClockwise,
  PhMoon,
  PhSparkle,
  PhSun,
} from "@phosphor-icons/vue";

defineProps<{
  darkMode: boolean;
  apiStatus: "checking" | "online" | "offline";
  workspaceConfigured: boolean;
}>();

const emit = defineEmits<{
  newResearch: [];
  showRecent: [];
  toggleTheme: [];
  openWorkspace: [];
}>();
</script>

<template>
  <header class="app-header">
    <div class="header-leading">
      <a class="brand" href="#main" aria-label="Evident home">
        <span class="brand-mark" aria-hidden="true"><PhSparkle :size="16" weight="fill" /></span>
        <span>Evident</span>
      </a>
      <nav class="product-nav" aria-label="Product navigation">
        <button class="product-nav-button active" type="button" @click="emit('newResearch')">Research</button>
        <button class="product-nav-button" type="button" @click="emit('showRecent')">
          <PhBookOpen :size="15" /> Library
        </button>
      </nav>
    </div>

    <nav class="header-actions" aria-label="Primary navigation">
      <span class="api-status" :class="`api-${apiStatus}`" role="status">
        <span class="api-status-dot" aria-hidden="true"></span>
        {{ apiStatus === "online" ? "API connected" : apiStatus === "offline" ? "API unavailable" : "Checking API" }}
      </span>
      <span class="header-divider" aria-hidden="true"></span>
      <button
        class="icon-button"
        type="button"
        :aria-label="darkMode ? 'Use light theme' : 'Use dark theme'"
        @click="emit('toggleTheme')"
      >
        <PhSun v-if="darkMode" :size="18" />
        <PhMoon v-else :size="18" />
      </button>
      <button
        class="workspace-button"
        type="button"
        :aria-label="workspaceConfigured ? 'Configure workspace' : 'Connect workspace'"
        @click="emit('openWorkspace')"
      >
        <PhClockCounterClockwise v-if="!workspaceConfigured" :size="15" />
        <span>{{ workspaceConfigured ? "Workspace" : "Connect" }}</span>
        <PhCaretDown :size="13" />
      </button>
      <button
        class="avatar-button"
        type="button"
        aria-label="Configure workspace"
        title="Configure workspace"
        @click="emit('openWorkspace')"
      >
        AK
      </button>
    </nav>
  </header>
</template>
