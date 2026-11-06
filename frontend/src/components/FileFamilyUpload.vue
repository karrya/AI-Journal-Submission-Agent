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
import { displayText, FILE_TYPE_LABELS } from '../utils/display'

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
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

async function submit(): Promise<void> {
  if (uploading.value) return
  error.value = ''
  conflict.value = false
  successMessage.value = ''
  if (!selectedFile.value) {
    error.value = '请选择要上传的文件。'
    return
  }
  if (existingMode.value && !selectedFamilyId.value) {
    error.value = '请选择现有文件族。'
    return
  }
  if (!existingMode.value && !displayName.value.trim()) {
    error.value = '请填写新文件族的显示名称。'
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
    successMessage.value = `已上传 ${uploaded.original_filename}，文件版本为 ${uploaded.file_version}。`
    emit('uploaded', uploaded)
  } catch (caught) {
    progress.value = null
    if (axios.isAxiosError(caught) && caught.response?.status === 409) {
      conflict.value = true
      error.value = '请先刷新当前稿件版本再重新上传，本次上传未自动重试。'
    } else {
      error.value = safeError(caught, '无法上传文件。')
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
      向现有文件族上传新版本
    </label>

    <label v-if="existingMode">现有文件族
      <select v-model="selectedFamilyId" data-test="file-family" required>
        <option value="">请选择文件族</option>
        <option v-for="family in families" :key="family.file_family_id" :value="family.file_family_id">
          {{ family.display_name }}（{{ displayText(FILE_TYPE_LABELS, family.file_type) }}，当前文件 v{{ family.file_version }}）
        </option>
      </select>
    </label>
    <template v-else>
      <label>文件类型
        <select v-model="fileType" data-test="file-type">
          <option v-for="type in FILE_TYPES" :key="type" :value="type">{{ displayText(FILE_TYPE_LABELS, type) }}</option>
        </select>
      </label>
      <label>文件族显示名称
        <input v-model="displayName" data-test="display-name" maxlength="255" required>
      </label>
    </template>

    <label>文件
      <input
        data-test="file-input"
        type="file"
        accept=".pdf,.doc,.docx,.rtf,.txt,.tex,.csv,.xls,.xlsx,.png,.jpg,.jpeg,.tif,.tiff"
        @change="fileChanged"
      >
    </label>
    <p class="upload-hint">支持 PDF、Office 文档、文本、CSV 和常见图片格式。大小限制提示：100 MiB。服务端必须校验文件内容，浏览器提示不构成安全检查。</p>
    <p v-if="selectedFile" data-test="file-hint">已选择：{{ selectedFile.name }} · {{ selectedFile.size }} 字节 · {{ selectedFile.type || '未知 MIME 类型' }}</p>
    <progress v-if="progress !== null" data-test="upload-progress" max="100" :value="progress">{{ progress }}%</progress>
    <span v-if="progress !== null">{{ progress }}%</span>
    <p v-if="successMessage" role="status">{{ successMessage }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button v-if="conflict" class="action-button action-button--neutral" type="button" data-test="refresh-version" @click="emit('refresh')">刷新稿件及当前版本</button>
    <button class="action-button action-button--create" type="submit" :disabled="uploading">上传文件</button>
  </form>
</template>
