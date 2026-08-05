<script setup lang="ts">
import KnowledgeLibrary from "../components/KnowledgeLibrary.vue";
import { useResearchStore } from "../stores/research";
import { useWorkspaceStore } from "../stores/workspace";

const researchStore = useResearchStore();
const workspaceStore = useWorkspaceStore();
</script>

<template>
  <KnowledgeLibrary
    :workspace="workspaceStore.workspace"
    @open-workspace="workspaceStore.openDialog()"
    @announce="researchStore.announcement = $event"
  />
</template>
