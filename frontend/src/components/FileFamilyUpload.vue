<script setup lang="ts">
import axios from 'axios'
import { computed, ref } from 'vue'
import { getSafeRequestId } from '../api/client'
import {
  FILE_TYPES,
  uploadFile,
  type FileType,
  type ManuscriptFile,
} from '../api/files'

const props = defineProps<{
  manuscriptId: string
  versionId: string
  currentFiles: ManuscriptFile[]
}>()

const emit = defineEmits<{
  uploaded: [file: ManuscriptFile]
  refresh: []
}>()

const existingMode = ref(false)
const selectedFamilyId = ref('')
const fileType = ref<FileType>('main_manuscript')
const displayName = ref('')
const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const progress = ref<number | null>(null)
const error = ref('')
const conflict = ref(false)
const successMessage = ref('')

const families = computed(() => {
  const unique = new Map<string, ManuscriptFile>()
  for (const file of props.currentFiles) {
    if (!unique.has(file.file_family_id)) unique.set(file.file_family_id, file)
  }
  return [...unique.values()]
})

function fileChanged(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  progress.value = null
  error.value = ''
  conflict.value = false
  successMessage.value = ''
}

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

async function submit(): Promise<void> {
  if (uploading.value) return
  error.value = ''
  conflict.value = false
  successMessage.value = ''
  if (!selectedFile.value) {
    error.value = 'Choose a file to upload.'
    return
  }
  if (existingMode.value && !selectedFamilyId.value) {
    error.value = 'Select an existing file family.'
    return
  }
  if (!existingMode.value && !displayName.value.trim()) {
    error.value = 'Enter a display name for the new file family.'
    return
  }

  uploading.value = true
  progress.value = 0
  try {
    const uploaded = await uploadFile(props.manuscriptId, props.versionId, {
      file: selectedFile.value,
      fileFamilyId: existingMode.value ? selectedFamilyId.value : undefined,
      fileType: existingMode.value ? undefined : fileType.value,
      displayName: existingMode.value ? undefined : displayName.value.trim(),
      onUploadProgress: (event) => {
        if (event.total && event.total > 0) {
          progress.value = Math.min(100, Math.round((event.loaded / event.total) * 100))
        }
      },
    })
    progress.value = 100
    successMessage.value = `Uploaded ${uploaded.original_filename} as file version ${uploaded.file_version}.`
    emit('uploaded', uploaded)
  } catch (caught) {
    progress.value = null
    if (axios.isAxiosError(caught) && caught.response?.status === 409) {
      conflict.value = true
      error.value = 'Refresh the current manuscript version before uploading again. The upload was not retried.'
    } else {
      error.value = safeError(caught, 'Unable to upload the file.')
    }
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <form class="stacked-form" novalidate @submit.prevent="submit">
    <label class="confirmation-control">
      <input v-model="existingMode" data-test="existing-family-mode" type="checkbox" :disabled="families.length === 0">
      Upload a new version to an existing file family
    </label>

    <label v-if="existingMode">Existing file family
      <select v-model="selectedFamilyId" data-test="file-family" required>
        <option value="">Select a family</option>
        <option v-for="family in families" :key="family.file_family_id" :value="family.file_family_id">
          {{ family.display_name }} ({{ family.file_type }}, current file v{{ family.file_version }})
        </option>
      </select>
    </label>
    <template v-else>
      <label>File type
        <select v-model="fileType" data-test="file-type">
          <option v-for="type in FILE_TYPES" :key="type" :value="type">{{ type.replaceAll('_', ' ') }}</option>
        </select>
      </label>
      <label>Family display name
        <input v-model="displayName" data-test="display-name" maxlength="255" required>
      </label>
    </template>

    <label>File
      <input
        data-test="file-input"
        type="file"
        accept=".pdf,.doc,.docx,.rtf,.txt,.tex,.csv,.xls,.xlsx,.png,.jpg,.jpeg,.tif,.tiff"
        @change="fileChanged"
      >
    </label>
    <p class="upload-hint">Accepted formats include PDF, Office documents, text, CSV, and common images. Size limit hint: 100 MiB. Server-side content validation is required; these browser hints are not security checks.</p>
    <p v-if="selectedFile" data-test="file-hint">Selected: {{ selectedFile.name }} · {{ selectedFile.size }} bytes · {{ selectedFile.type || 'unknown MIME type' }}</p>
    <progress v-if="progress !== null" data-test="upload-progress" max="100" :value="progress">{{ progress }}%</progress>
    <span v-if="progress !== null">{{ progress }}%</span>
    <p v-if="successMessage" role="status">{{ successMessage }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button v-if="conflict" type="button" data-test="refresh-version" @click="emit('refresh')">Refresh manuscript and current version</button>
    <button type="submit" :disabled="uploading">Upload file</button>
  </form>
</template>
