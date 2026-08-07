<script setup lang="ts">
import { PhBookOpen, PhBriefcase, PhMoon, PhSun } from "@phosphor-icons/vue";
import { computed } from "vue";

import evidentMark from "../assets/evident-mark.png";
import ProfileMenu from "./ProfileMenu.vue";

const props = defineProps<{
  darkMode: boolean;
  apiStatus: "checking" | "online" | "offline";
  tenantName: string;
  userDisplayName: string | null;
  userEmail: string;
  activePage: "research" | "knowledge";
}>();

const emit = defineEmits<{
  newResearch: [];
  showRecent: [];
  showKnowledge: [];
  toggleTheme: [];
  editProfile: [];
  logout: [];
}>();

const userInitials = computed(() => {
  const source = props.userDisplayName?.trim();
  if (!source) return "?";

  return (
    source
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "?"
  );
});
</script>

<template>
  <header class="app-header">
    <div class="header-leading">
      <a class="brand" href="#main" aria-label="Evident home">
        <img class="brand-mark" :src="evidentMark" alt="" width="34" height="34" />
        <span>Evident</span>
      </a>
      <nav class="product-nav" aria-label="Product navigation">
        <button
          class="product-nav-button"
          :class="{ active: activePage === 'research' }"
          type="button"
          @click="emit('newResearch')"
        >
          Research
        </button>
        <button
          class="product-nav-button"
          :class="{ active: activePage === 'knowledge' }"
          type="button"
          @click="emit('showKnowledge')"
        >
          <PhBookOpen :size="15" /> Private Knowledge
        </button>
      </nav>
    </div>

    <nav class="header-actions" aria-label="Primary navigation">
      <span class="api-status" :class="`api-${apiStatus}`" role="status">
        <span class="api-status-dot" aria-hidden="true"></span>
        {{
          apiStatus === "online"
            ? "API connected"
            : apiStatus === "offline"
              ? "API unavailable"
              : "Checking API"
        }}
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
      <span class="workspace-pill" aria-label="Current workspace">
        <PhBriefcase :size="16" />
        <span>{{ tenantName }}</span>
      </span>
      <ProfileMenu
        :user-display-name="userDisplayName"
        :user-email="userEmail"
        :tenant-name="tenantName"
        :initials="userInitials"
        @edit-profile="emit('editProfile')"
        @logout="emit('logout')"
      />
    </nav>
  </header>
</template>
