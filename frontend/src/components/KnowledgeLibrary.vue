<script setup lang="ts">
import {
  PhArrowClockwise,
  PhCheckCircle,
  PhFileText,
  PhLockKey,
  PhTrash,
  PhUploadSimple,
  PhWarningCircle,
} from "@phosphor-icons/vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";

import {
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  ResearchApiError,
  uploadKnowledgeDocument,
} from "../lib/research-api";
import { useAuthStore } from "../stores/auth";
import type { KnowledgeDocument } from "../types/research";

const emit = defineEmits<{
  announce: [message: string];
}>();

const authStore = useAuthStore();
const pendingDeleteId = ref<string | null>(null);
const selectedFile = ref<File | null>(null);
const errorMessage = ref("");
const fileInput = ref<HTMLInputElement | null>(null);

const acceptedTypes = ".txt,.md,.markdown,.pdf";

const queryClient = useQueryClient();
const documentsQueryKey = computed(() => ["documents", authStore.tenant?.id]);

const {
  data: documents,
  isFetching: loading,
  error: listError,
  refetch: refreshDocuments,
} = useQuery({
  queryKey: documentsQueryKey,
  queryFn: () => listKnowledgeDocuments(),
  retry: false,
  initialData: [],
});

watch(listError, (error) => {
  if (error) {
    errorMessage.value = describeError(
      error,
      "Private knowledge could not be loaded. Your existing documents remain safe.",
    );
  }
});

const uploadMutation = useMutation({
  mutationFn: (file: File) => uploadKnowledgeDocument(file),
  onSuccess: (created) => {
    queryClient.setQueryData<KnowledgeDocument[]>(documentsQueryKey.value, (current) => [
      created,
      ...(current ?? []).filter((item) => item.id !== created.id),
    ]);
    selectedFile.value = null;
    if (fileInput.value) fileInput.value.value = "";
    emit("announce", `${created.filename} is indexed and ready for research.`);
  },
});
const uploading = computed(() => uploadMutation.isPending.value);

const deleteMutation = useMutation({
  mutationFn: (document: KnowledgeDocument) => deleteKnowledgeDocument(document.id),
  onSuccess: (_result, document) => {
    queryClient.setQueryData<KnowledgeDocument[]>(documentsQueryKey.value, (current) =>
      (current ?? []).filter((item) => item.id !== document.id),
    );
    pendingDeleteId.value = null;
    emit("announce", `${document.filename} and its indexed evidence were deleted.`);
  },
});
const deletingId = computed(() =>
  deleteMutation.isPending.value ? (deleteMutation.variables.value?.id ?? null) : null,
);

function readableBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function readableDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(status: KnowledgeDocument["status"]): string {
  return {
    pending: "Pending",
    indexing: "Indexing",
    ready: "Ready",
    failed: "Needs attention",
    deleting: "Deleting",
  }[status];
}

function selectFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  errorMessage.value = "";
}

async function retryList(): Promise<void> {
  errorMessage.value = "";
  await refreshDocuments();
}

function describeError(error: unknown, fallback: string): string {
  return error instanceof ResearchApiError ? error.message : fallback;
}

async function uploadSelected(): Promise<void> {
  if (!selectedFile.value || uploading.value) return;

  errorMessage.value = "";
  try {
    await uploadMutation.mutateAsync(selectedFile.value);
  } catch (error) {
    errorMessage.value = describeError(
      error,
      "The document could not be uploaded. No successful indexing is being claimed.",
    );
  }
}

async function confirmDelete(document: KnowledgeDocument): Promise<void> {
  if (pendingDeleteId.value !== document.id) {
    pendingDeleteId.value = document.id;
    return;
  }

  errorMessage.value = "";
  try {
    await deleteMutation.mutateAsync(document);
  } catch (error) {
    errorMessage.value = describeError(
      error,
      "The document could not be fully deleted. Its lifecycle remains visible for recovery.",
    );
  }
}
</script>

<template>
  <main id="main" class="knowledge-page" tabindex="-1">
    <section class="knowledge-heading" aria-labelledby="knowledge-title">
      <div>
        <p class="hero-eyebrow">Private Knowledge</p>
        <h1 id="knowledge-title">Bring your own evidence.</h1>
        <p>
          Add source documents once, then let the Local Scout retrieve tenant-scoped evidence in
          every deep-research run.
        </p>
      </div>
      <div class="knowledge-trust-note">
        <PhLockKey :size="18" aria-hidden="true" />
        <span>Source files, vectors, and metadata stay inside the active tenant boundary.</span>
      </div>
    </section>

    <section class="upload-card" aria-labelledby="upload-title">
      <div class="upload-copy">
        <span class="upload-icon" aria-hidden="true"><PhUploadSimple :size="22" /></span>
        <div>
          <h2 id="upload-title">Upload a source document</h2>
          <p>TXT, Markdown, or text-based PDF. Maximum 10 MB.</p>
        </div>
      </div>
      <div class="upload-controls">
        <label class="file-picker">
          <input ref="fileInput" type="file" :accept="acceptedTypes" @change="selectFile" />
          <span>{{ selectedFile?.name ?? "Choose document" }}</span>
        </label>
        <button
          class="primary-button"
          type="button"
          :disabled="!selectedFile || uploading"
          @click="uploadSelected"
        >
          <PhUploadSimple :size="17" />
          {{ uploading ? "Validating and indexing…" : "Upload and index" }}
        </button>
      </div>
    </section>

    <section v-if="errorMessage" class="knowledge-error" role="alert">
      <PhWarningCircle :size="20" aria-hidden="true" />
      <div>
        <strong>Private Knowledge needs attention</strong>
        <p>{{ errorMessage }}</p>
      </div>
      <button class="secondary-button" type="button" @click="retryList">
        <PhArrowClockwise :size="15" /> Retry
      </button>
    </section>

    <section class="document-library" aria-labelledby="library-title" :aria-busy="loading">
      <div class="document-library-heading">
        <div>
          <p class="eyebrow">Evidence library</p>
          <h2 id="library-title">Indexed documents</h2>
        </div>
        <button class="secondary-button" type="button" :disabled="loading" @click="retryList">
          <PhArrowClockwise :size="15" /> {{ loading ? "Refreshing…" : "Refresh" }}
        </button>
      </div>

      <div v-if="!loading && documents?.length === 0" class="knowledge-empty">
        <PhFileText :size="30" aria-hidden="true" />
        <h3>No private sources yet</h3>
        <p>Upload the first document to give Local Scout evidence it can cite.</p>
      </div>

      <ul v-else class="document-list">
        <li v-for="document in documents" :key="document.id" class="document-row">
          <span class="document-icon" aria-hidden="true"><PhFileText :size="20" /></span>
          <div class="document-primary">
            <strong>{{ document.filename }}</strong>
            <span
              >{{ readableBytes(document.byte_size) }} · Added
              {{ readableDate(document.created_at) }}</span
            >
            <p v-if="document.error_message">{{ document.error_message }}</p>
          </div>
          <span class="document-status" :class="`document-status-${document.status}`">
            <PhCheckCircle v-if="document.status === 'ready'" :size="15" aria-hidden="true" />
            <PhWarningCircle
              v-else-if="document.status === 'failed'"
              :size="15"
              aria-hidden="true"
            />
            {{ statusLabel(document.status) }}
          </span>
          <div class="document-actions">
            <button
              v-if="pendingDeleteId === document.id"
              class="document-cancel"
              type="button"
              @click="pendingDeleteId = null"
            >
              Cancel
            </button>
            <button
              class="document-delete"
              :class="{ 'confirm-delete': pendingDeleteId === document.id }"
              type="button"
              :disabled="deletingId === document.id || document.status === 'deleting'"
              :aria-label="`${pendingDeleteId === document.id ? 'Confirm deletion of' : 'Delete'} ${document.filename}`"
              @click="confirmDelete(document)"
            >
              <PhTrash :size="16" aria-hidden="true" />
              {{
                deletingId === document.id
                  ? "Deleting…"
                  : pendingDeleteId === document.id
                    ? "Confirm"
                    : "Delete"
              }}
            </button>
          </div>
        </li>
      </ul>
    </section>
  </main>
</template>
