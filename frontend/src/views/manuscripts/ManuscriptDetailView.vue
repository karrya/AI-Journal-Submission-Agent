<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { listAuthors, type AuthorResponse } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import { downloadFile, listFiles, type ManuscriptFile } from '../../api/files'
import {
  createManuscriptVersion,
  getManuscript,
  getManuscriptVersion,
  listManuscriptVersions,
  replaceManuscriptAuthors,
  updateManuscript,
  type Manuscript,
  type ManuscriptAuthorsUpdate,
  type ManuscriptVersion,
} from '../../api/manuscripts'
import { fetchAllPages } from '../../api/pagination'
import AuthorshipEditor from '../../components/AuthorshipEditor.vue'
import FileFamilyUpload from '../../components/FileFamilyUpload.vue'
import { useAuthStore } from '../../stores/auth'
import {
  displayText,
  FILE_INTEGRITY_LABELS,
  FILE_SCAN_LABELS,
  FILE_TYPE_LABELS,
  MANUSCRIPT_STATUS_LABELS,
} from '../../utils/display'

const props = defineProps<{ manuscriptId: string }>()
const auth = useAuthStore()
const canManage = computed(() => auth.user?.roles.some(
  (role) => role === 'system_admin' || role === 'submission_operator',
) ?? false)

const manuscript = ref<Manuscript | null>(null)
const versions = ref<ManuscriptVersion[]>([])
const currentVersion = ref<ManuscriptVersion | null>(null)
const currentFiles = ref<ManuscriptFile[]>([])
const authorOptions = ref<AuthorResponse[]>([])
const loading = ref(false)
const errorMessage = ref('')
const metadataBusy = ref(false)
const metadataError = ref('')
const authorshipBusy = ref(false)
const authorshipError = ref('')
const authorshipFormKey = ref(0)
const versionBusy = ref(false)
const versionError = ref('')
const versionLabel = ref('')
const versionNote = ref('')
const downloadingId = ref<string | null>(null)
const fileError = ref('')
let loadSequence = 0

const metadata = reactive({
  title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: '',
  funding_statement: '', conflict_of_interest_statement: '', ethics_statement: '',
  data_availability_statement: '', notes: '',
})

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

function isCurrent(sequence: number): boolean {
  return sequence === loadSequence
}

function syncMetadata(value: Manuscript): void {
  Object.assign(metadata, {
    title: value.title,
    abstract: value.abstract,
    keywords: value.keywords.join(', '),
    article_type: value.article_type,
    subject_field: value.subject_field ?? '',
    language: value.language,
    funding_statement: value.funding_statement ?? '',
    conflict_of_interest_statement: value.conflict_of_interest_statement ?? '',
    ethics_statement: value.ethics_statement ?? '',
    data_availability_statement: value.data_availability_statement ?? '',
    notes: value.notes ?? '',
  })
}

async function loadCurrentVersion(sequence: number, manuscriptId: string, versionId: string | null): Promise<void> {
  currentVersion.value = null
  currentFiles.value = []
  if (!versionId) return
  const version = await getManuscriptVersion(manuscriptId, versionId)
  if (!isCurrent(sequence)) return
  currentVersion.value = version
  const files = await fetchAllPages((page, pageSize) => listFiles(
    manuscriptId, versionId, { page, page_size: pageSize },
  ))
  if (!isCurrent(sequence)) return
  currentFiles.value = files.items
}

function clearWorkspace(): void {
  manuscript.value = null
  versions.value = []
  currentVersion.value = null
  currentFiles.value = []
  authorOptions.value = []
  Object.assign(metadata, {
    title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: '',
    funding_statement: '', conflict_of_interest_statement: '', ethics_statement: '',
    data_availability_statement: '', notes: '',
  })
  metadataError.value = ''
  authorshipError.value = ''
  versionError.value = ''
  fileError.value = ''
}

async function loadWorkspace(): Promise<void> {
  const manuscriptId = props.manuscriptId
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  metadataBusy.value = false
  authorshipBusy.value = false
  try {
    const result = await getManuscript(manuscriptId)
    if (!isCurrent(sequence)) return
    manuscript.value = result
    syncMetadata(result)
    const [versionPage, authors] = await Promise.all([
      fetchAllPages((page, pageSize) => listManuscriptVersions(
        manuscriptId, { page, page_size: pageSize },
      )),
      fetchAllPages((page, pageSize) => listAuthors({
        page, page_size: pageSize, sort: 'display_name', order: 'asc',
      })),
    ])
    if (!isCurrent(sequence)) return
    versions.value = versionPage.items
    authorOptions.value = authors.items
    await loadCurrentVersion(sequence, manuscriptId, result.current_version_id)
  } catch (error) {
    if (!isCurrent(sequence)) return
    errorMessage.value = safeError(error, '无法加载稿件工作区。')
    currentVersion.value = null
    currentFiles.value = []
  } finally {
    if (isCurrent(sequence)) loading.value = false
  }
}

async function refreshCurrentWorkspace(): Promise<void> {
  const manuscriptId = props.manuscriptId
  const sequence = ++loadSequence
  loading.value = true
  metadataBusy.value = false
  authorshipBusy.value = false
  fileError.value = ''
  try {
    const result = await getManuscript(manuscriptId)
    if (!isCurrent(sequence)) return
    manuscript.value = result
    syncMetadata(result)
    await loadCurrentVersion(sequence, manuscriptId, result.current_version_id)
  } catch (error) {
    if (!isCurrent(sequence)) return
    currentVersion.value = null
    currentFiles.value = []
    fileError.value = safeError(error, '无法刷新当前版本和文件。')
  } finally {
    if (isCurrent(sequence)) loading.value = false
  }
}

function nullable(value: string): string | null {
  return value.trim() || null
}

async function saveMetadata(): Promise<void> {
  const current = manuscript.value
  if (metadataBusy.value || !current || current.id !== props.manuscriptId || !canManage.value) return
  const manuscriptId = current.id
  metadataError.value = ''
  if (!metadata.title.trim() || !metadata.abstract.trim() || !metadata.article_type.trim() || !metadata.language.trim()) {
    metadataError.value = '请填写标题、摘要、文章类型和语言。'
    return
  }
  const sequence = loadSequence
  metadataBusy.value = true
  try {
    const result = await updateManuscript(manuscriptId, {
      title: metadata.title.trim(),
      abstract: metadata.abstract.trim(),
      keywords: metadata.keywords.split(',').map((keyword) => keyword.trim()).filter(Boolean),
      article_type: metadata.article_type.trim(),
      subject_field: nullable(metadata.subject_field),
      language: metadata.language.trim(),
      funding_statement: nullable(metadata.funding_statement),
      conflict_of_interest_statement: nullable(metadata.conflict_of_interest_statement),
      ethics_statement: nullable(metadata.ethics_statement),
      data_availability_statement: nullable(metadata.data_availability_statement),
      notes: nullable(metadata.notes),
    })
    if (!isCurrent(sequence) || !manuscript.value) return
    manuscript.value = {
      ...manuscript.value,
      title: result.title,
      abstract: result.abstract,
      keywords: result.keywords,
      article_type: result.article_type,
      subject_field: result.subject_field,
      language: result.language,
      funding_statement: result.funding_statement,
      conflict_of_interest_statement: result.conflict_of_interest_statement,
      ethics_statement: result.ethics_statement,
      data_availability_statement: result.data_availability_statement,
      notes: result.notes,
      updated_at: result.updated_at,
    }
    syncMetadata(result)
  } catch (error) {
    if (isCurrent(sequence)) metadataError.value = safeError(error, '无法更新稿件元数据。')
  } finally {
    if (isCurrent(sequence)) metadataBusy.value = false
  }
}

async function saveAuthorship(payload: ManuscriptAuthorsUpdate): Promise<void> {
  const current = manuscript.value
  if (authorshipBusy.value || !current || current.id !== props.manuscriptId || !canManage.value) return
  const manuscriptId = current.id
  const sequence = loadSequence
  authorshipBusy.value = true
  authorshipError.value = ''
  try {
    const authors = await replaceManuscriptAuthors(manuscriptId, payload)
    if (!isCurrent(sequence) || !manuscript.value) return
    manuscript.value = { ...manuscript.value, authors }
    authorshipFormKey.value += 1
  } catch (error) {
    if (isCurrent(sequence)) authorshipError.value = safeError(error, '无法更新作者名单。')
  } finally {
    if (isCurrent(sequence)) authorshipBusy.value = false
  }
}

async function saveVersion(): Promise<void> {
  const current = manuscript.value
  if (versionBusy.value || !current || current.id !== props.manuscriptId || !canManage.value) return
  const manuscriptId = current.id
  const sequence = loadSequence
  versionBusy.value = true
  versionError.value = ''
  try {
    await createManuscriptVersion(manuscriptId, {
      label: nullable(versionLabel.value),
      change_note: nullable(versionNote.value),
    })
    if (!isCurrent(sequence)) {
      versionError.value = '稿件版本已创建，请刷新工作区后再创建其他版本。'
      return
    }
    versionLabel.value = ''
    versionNote.value = ''
    await loadWorkspace()
  } catch (error) {
    versionError.value = safeError(error, '稿件版本可能已创建，请刷新后重试。')
  } finally {
    versionBusy.value = false
  }
}

async function download(file: ManuscriptFile): Promise<void> {
  if (downloadingId.value) return
  downloadingId.value = file.id
  fileError.value = ''
  let objectUrl: string | null = null
  let anchor: HTMLAnchorElement | null = null
  try {
    const blob = await downloadFile(file.id)
    objectUrl = URL.createObjectURL(blob)
    anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = file.original_filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
  } catch (error) {
    fileError.value = safeError(error, '无法下载文件。')
  } finally {
    try {
      anchor?.remove()
    } catch {
      // 即使 DOM 移除失败，也必须继续释放对象 URL。
    }
    if (objectUrl) {
      const url = objectUrl
      setTimeout(() => URL.revokeObjectURL(url), 0)
    }
    downloadingId.value = null
  }
}

watch(() => props.manuscriptId, () => {
  clearWorkspace()
  void loadWorkspace()
}, { immediate: true, flush: 'sync' })
</script>

<template>
  <section class="management-page" aria-labelledby="manuscript-detail-title">
    <RouterLink to="/manuscripts">返回稿件列表</RouterLink>
    <p v-if="loading">正在加载稿件工作区…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <template v-if="manuscript">
      <header>
        <h1 id="manuscript-detail-title">{{ manuscript.title }}</h1>
        <p>{{ manuscript.internal_number }} · {{ displayText(MANUSCRIPT_STATUS_LABELS, manuscript.status) }}</p>
        <p v-if="currentVersion">当前版本：{{ currentVersion.version_number }}<span v-if="currentVersion.label"> · {{ currentVersion.label }}</span></p>
        <p v-else>暂无当前版本。</p>
      </header>

      <section aria-labelledby="working-metadata-title">
        <h2 id="working-metadata-title">工作元数据</h2>
        <form v-if="canManage && manuscript.status !== 'archived'" data-test="metadata-form" class="stacked-form" novalidate @submit.prevent="saveMetadata">
          <div class="form-grid">
            <label>标题<input v-model="metadata.title" data-test="metadata-title" maxlength="1000" required></label>
            <label>文章类型<input v-model="metadata.article_type" maxlength="100" required></label>
            <label>语言<input v-model="metadata.language" maxlength="32" required></label>
            <label>学科领域<input v-model="metadata.subject_field" maxlength="255"></label>
            <label>关键词（以逗号分隔）<input v-model="metadata.keywords"></label>
          </div>
          <label>摘要<textarea v-model="metadata.abstract" rows="6" required></textarea></label>
          <label>基金声明<textarea v-model="metadata.funding_statement" rows="3"></textarea></label>
          <label>利益冲突声明<textarea v-model="metadata.conflict_of_interest_statement" rows="3"></textarea></label>
          <label>伦理声明<textarea v-model="metadata.ethics_statement" rows="3"></textarea></label>
          <label>数据可用性声明<textarea v-model="metadata.data_availability_statement" rows="3"></textarea></label>
          <label>备注<textarea v-model="metadata.notes" rows="3"></textarea></label>
          <p v-if="metadataError" class="form-error" role="alert">{{ metadataError }}</p>
          <button type="submit" :disabled="metadataBusy">保存工作元数据</button>
        </form>
        <dl v-else class="detail-grid">
          <div><dt>标题</dt><dd>{{ manuscript.title }}</dd></div>
          <div><dt>摘要</dt><dd>{{ manuscript.abstract }}</dd></div>
          <div><dt>关键词</dt><dd>{{ manuscript.keywords.join(', ') || '—' }}</dd></div>
          <div><dt>文章类型</dt><dd>{{ manuscript.article_type }}</dd></div>
          <div><dt>语言</dt><dd>{{ manuscript.language }}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="authorship-title">
        <h2 id="authorship-title">作者名单及顺序</h2>
        <p>仅提交作者 ID、位置和通讯作者标记，显示姓名为只读。</p>
        <AuthorshipEditor
          v-if="canManage && manuscript.status !== 'archived'"
          :key="authorshipFormKey"
          data-test="authorship-form"
          :model-value="manuscript.authors"
          :owner-author-id="manuscript.owner_author_id"
          :available-authors="authorOptions"
          :submitting="authorshipBusy"
          @submit="saveAuthorship"
        />
        <ol v-else>
          <li v-for="author in manuscript.authors" :key="author.author_id">
            {{ author.position }}. {{ author.display_name }}<span v-if="author.is_corresponding"> · 通讯作者</span>
          </li>
        </ol>
        <p v-if="authorshipError" class="form-error" role="alert">{{ authorshipError }}</p>
      </section>

      <section v-if="canManage && manuscript.status !== 'archived'" aria-labelledby="new-version-title">
        <h2 id="new-version-title">创建不可变稿件版本</h2>
        <p>创建版本会为当前工作元数据和作者名单生成快照，现有快照永不更改。</p>
        <form data-test="version-form" class="stacked-form" @submit.prevent="saveVersion">
          <label>版本标签<input v-model="versionLabel" data-test="version-label" maxlength="100"></label>
          <label>变更说明<textarea v-model="versionNote" rows="3"></textarea></label>
          <button type="submit" :disabled="versionBusy">创建新稿件版本</button>
        </form>
        <p v-if="versionError" class="form-error" role="alert">{{ versionError }}</p>
      </section>

      <section data-test="snapshot-history" aria-labelledby="snapshot-history-title">
        <h2 id="snapshot-history-title">不可变快照历史</h2>
        <details v-for="version in versions" :key="version.id" :open="version.id === manuscript.current_version_id">
          <summary>版本 {{ version.version_number }}<span v-if="version.label"> · {{ version.label }}</span><span v-if="version.id === manuscript.current_version_id"> · 当前版本</span></summary>
          <p><time :datetime="version.created_at">{{ version.created_at }}</time></p>
          <p v-if="version.change_note">{{ version.change_note }}</p>
          <dl class="detail-grid">
            <div><dt>标题</dt><dd>{{ version.metadata_snapshot.title }}</dd></div>
            <div><dt>摘要</dt><dd>{{ version.metadata_snapshot.abstract }}</dd></div>
            <div><dt>关键词</dt><dd>{{ version.metadata_snapshot.keywords.join(', ') || '—' }}</dd></div>
            <div><dt>文章类型</dt><dd>{{ version.metadata_snapshot.article_type }}</dd></div>
            <div><dt>学科领域</dt><dd>{{ version.metadata_snapshot.subject_field ?? '—' }}</dd></div>
            <div><dt>语言</dt><dd>{{ version.metadata_snapshot.language }}</dd></div>
            <div><dt>基金声明</dt><dd>{{ version.metadata_snapshot.funding_statement ?? '—' }}</dd></div>
            <div><dt>利益冲突</dt><dd>{{ version.metadata_snapshot.conflict_of_interest_statement ?? '—' }}</dd></div>
            <div><dt>伦理声明</dt><dd>{{ version.metadata_snapshot.ethics_statement ?? '—' }}</dd></div>
            <div><dt>数据可用性</dt><dd>{{ version.metadata_snapshot.data_availability_statement ?? '—' }}</dd></div>
            <div><dt>备注</dt><dd>{{ version.metadata_snapshot.notes ?? '—' }}</dd></div>
          </dl>
          <ol class="authorship-position-list" data-test="snapshot-authorship">
            <li v-for="author in version.metadata_snapshot.authors" :key="author.author_id">
              {{ author.position }}. {{ author.display_name }}<span v-if="author.is_corresponding"> · 通讯作者</span>
            </li>
          </ol>
        </details>
      </section>

      <section data-test="current-files" aria-labelledby="current-files-title">
        <h2 id="current-files-title">当前版本文件</h2>
        <p v-if="fileError" class="form-error" role="alert">{{ fileError }}</p>
        <FileFamilyUpload
          v-if="currentVersion && currentVersion.id === manuscript.current_version_id && canManage && manuscript.status !== 'archived'"
          :manuscript-id="manuscript.id"
          :version-id="currentVersion.id"
          :current-files="currentFiles"
          @uploaded="refreshCurrentWorkspace"
          @refresh="refreshCurrentWorkspace"
        />
        <p v-if="!currentVersion">请先刷新稿件，再管理文件。</p>
        <p v-else-if="currentFiles.length === 0">当前版本暂无文件。</p>
        <table v-else>
          <thead><tr><th>文件族</th><th>类型</th><th>文件版本</th><th>原始文件名</th><th>大小</th><th>完整性</th><th>扫描状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="file in currentFiles" :key="file.id">
            <td>{{ file.display_name }}</td><td>{{ displayText(FILE_TYPE_LABELS, file.file_type) }}</td><td>{{ file.file_version }}</td>
            <td>{{ file.original_filename }}</td><td>{{ file.size_bytes }} 字节</td>
            <td>{{ displayText(FILE_INTEGRITY_LABELS, file.integrity_status) }}</td><td>{{ displayText(FILE_SCAN_LABELS, file.scan_status) }}</td>
            <td><button type="button" :data-test="`download-${file.id}`" :disabled="downloadingId !== null" @click="download(file)">下载</button></td>
          </tr></tbody>
        </table>
      </section>
    </template>
  </section>
</template>
