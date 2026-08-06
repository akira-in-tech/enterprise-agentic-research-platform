<script setup lang="ts">
import KnowledgeLibrary from "../components/KnowledgeLibrary.vue";
import { useResearchStore } from "../stores/research";

const researchStore = useResearchStore();
</script>

<template>
  <KnowledgeLibrary @announce="researchStore.announcement = $event" />
</template>
