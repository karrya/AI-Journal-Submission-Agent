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
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
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
    errorMessage.value = safeError(error, 'Unable to load the manuscript workspace.')
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
    fileError.value = safeError(error, 'Unable to refresh the current version and files.')
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
    metadataError.value = 'Title, abstract, article type, and language are required.'
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
    if (isCurrent(sequence)) metadataError.value = safeError(error, 'Unable to update manuscript metadata.')
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
    if (isCurrent(sequence)) authorshipError.value = safeError(error, 'Unable to update authorship.')
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
      versionError.value = 'The version was created. Refresh the workspace before creating another version.'
      return
    }
    versionLabel.value = ''
    versionNote.value = ''
    await loadWorkspace()
  } catch (error) {
    versionError.value = safeError(error, 'The version may have been created; refresh before trying again.')
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
    fileError.value = safeError(error, 'Unable to download the file.')
  } finally {
    try {
      anchor?.remove()
    } catch {
      // Cleanup must still revoke the object URL if DOM removal fails.
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
    <RouterLink to="/manuscripts">Back to manuscripts</RouterLink>
    <p v-if="loading">Loading manuscript workspace…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <template v-if="manuscript">
      <header>
        <h1 id="manuscript-detail-title">{{ manuscript.title }}</h1>
        <p>{{ manuscript.internal_number }} · {{ manuscript.status }}</p>
        <p v-if="currentVersion">Current version: {{ currentVersion.version_number }}<span v-if="currentVersion.label"> · {{ currentVersion.label }}</span></p>
        <p v-else>No current version is available.</p>
      </header>

      <section aria-labelledby="working-metadata-title">
        <h2 id="working-metadata-title">Working metadata</h2>
        <form v-if="canManage && manuscript.status !== 'archived'" data-test="metadata-form" class="stacked-form" novalidate @submit.prevent="saveMetadata">
          <div class="form-grid">
            <label>Title<input v-model="metadata.title" data-test="metadata-title" maxlength="1000" required></label>
            <label>Article type<input v-model="metadata.article_type" maxlength="100" required></label>
            <label>Language<input v-model="metadata.language" maxlength="32" required></label>
            <label>Subject field<input v-model="metadata.subject_field" maxlength="255"></label>
            <label>Keywords (comma separated)<input v-model="metadata.keywords"></label>
          </div>
          <label>Abstract<textarea v-model="metadata.abstract" rows="6" required></textarea></label>
          <label>Funding statement<textarea v-model="metadata.funding_statement" rows="3"></textarea></label>
          <label>Conflict of interest statement<textarea v-model="metadata.conflict_of_interest_statement" rows="3"></textarea></label>
          <label>Ethics statement<textarea v-model="metadata.ethics_statement" rows="3"></textarea></label>
          <label>Data availability statement<textarea v-model="metadata.data_availability_statement" rows="3"></textarea></label>
          <label>Notes<textarea v-model="metadata.notes" rows="3"></textarea></label>
          <p v-if="metadataError" class="form-error" role="alert">{{ metadataError }}</p>
          <button type="submit" :disabled="metadataBusy">Save working metadata</button>
        </form>
        <dl v-else class="detail-grid">
          <div><dt>Title</dt><dd>{{ manuscript.title }}</dd></div>
          <div><dt>Abstract</dt><dd>{{ manuscript.abstract }}</dd></div>
          <div><dt>Keywords</dt><dd>{{ manuscript.keywords.join(', ') || '—' }}</dd></div>
          <div><dt>Article type</dt><dd>{{ manuscript.article_type }}</dd></div>
          <div><dt>Language</dt><dd>{{ manuscript.language }}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="authorship-title">
        <h2 id="authorship-title">Ordered authorship</h2>
        <p>Only author IDs, positions, and corresponding-author flags are submitted. Display names are read-only.</p>
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
            {{ author.position }}. {{ author.display_name }}<span v-if="author.is_corresponding"> · Corresponding author</span>
          </li>
        </ol>
        <p v-if="authorshipError" class="form-error" role="alert">{{ authorshipError }}</p>
      </section>

      <section v-if="canManage && manuscript.status !== 'archived'" aria-labelledby="new-version-title">
        <h2 id="new-version-title">Create immutable version</h2>
        <p>Creating a version snapshots the current working metadata and authorship. Existing snapshots never change.</p>
        <form data-test="version-form" class="stacked-form" @submit.prevent="saveVersion">
          <label>Version label<input v-model="versionLabel" data-test="version-label" maxlength="100"></label>
          <label>Change note<textarea v-model="versionNote" rows="3"></textarea></label>
          <button type="submit" :disabled="versionBusy">Create new version</button>
        </form>
        <p v-if="versionError" class="form-error" role="alert">{{ versionError }}</p>
      </section>

      <section data-test="snapshot-history" aria-labelledby="snapshot-history-title">
        <h2 id="snapshot-history-title">Immutable snapshot history</h2>
        <details v-for="version in versions" :key="version.id" :open="version.id === manuscript.current_version_id">
          <summary>Version {{ version.version_number }}<span v-if="version.label"> · {{ version.label }}</span><span v-if="version.id === manuscript.current_version_id"> · Current</span></summary>
          <p><time :datetime="version.created_at">{{ version.created_at }}</time></p>
          <p v-if="version.change_note">{{ version.change_note }}</p>
          <dl class="detail-grid">
            <div><dt>Title</dt><dd>{{ version.metadata_snapshot.title }}</dd></div>
            <div><dt>Abstract</dt><dd>{{ version.metadata_snapshot.abstract }}</dd></div>
            <div><dt>Keywords</dt><dd>{{ version.metadata_snapshot.keywords.join(', ') || '—' }}</dd></div>
            <div><dt>Article type</dt><dd>{{ version.metadata_snapshot.article_type }}</dd></div>
            <div><dt>Subject field</dt><dd>{{ version.metadata_snapshot.subject_field ?? '—' }}</dd></div>
            <div><dt>Language</dt><dd>{{ version.metadata_snapshot.language }}</dd></div>
            <div><dt>Funding</dt><dd>{{ version.metadata_snapshot.funding_statement ?? '—' }}</dd></div>
            <div><dt>Conflict of interest</dt><dd>{{ version.metadata_snapshot.conflict_of_interest_statement ?? '—' }}</dd></div>
            <div><dt>Ethics</dt><dd>{{ version.metadata_snapshot.ethics_statement ?? '—' }}</dd></div>
            <div><dt>Data availability</dt><dd>{{ version.metadata_snapshot.data_availability_statement ?? '—' }}</dd></div>
            <div><dt>Notes</dt><dd>{{ version.metadata_snapshot.notes ?? '—' }}</dd></div>
          </dl>
          <ol class="authorship-position-list" data-test="snapshot-authorship">
            <li v-for="author in version.metadata_snapshot.authors" :key="author.author_id">
              {{ author.position }}. {{ author.display_name }}<span v-if="author.is_corresponding"> · Corresponding author</span>
            </li>
          </ol>
        </details>
      </section>

      <section data-test="current-files" aria-labelledby="current-files-title">
        <h2 id="current-files-title">Current-version files</h2>
        <p v-if="fileError" class="form-error" role="alert">{{ fileError }}</p>
        <FileFamilyUpload
          v-if="currentVersion && currentVersion.id === manuscript.current_version_id && canManage && manuscript.status !== 'archived'"
          :manuscript-id="manuscript.id"
          :version-id="currentVersion.id"
          :current-files="currentFiles"
          @uploaded="refreshCurrentWorkspace"
          @refresh="refreshCurrentWorkspace"
        />
        <p v-if="!currentVersion">Refresh the manuscript before managing files.</p>
        <p v-else-if="currentFiles.length === 0">No files in the current version.</p>
        <table v-else>
          <thead><tr><th>Family</th><th>Type</th><th>File version</th><th>Original filename</th><th>Size</th><th>Integrity</th><th>Scan</th><th>Actions</th></tr></thead>
          <tbody><tr v-for="file in currentFiles" :key="file.id">
            <td>{{ file.display_name }}</td><td>{{ file.file_type }}</td><td>{{ file.file_version }}</td>
            <td>{{ file.original_filename }}</td><td>{{ file.size_bytes }} bytes</td>
            <td>{{ file.integrity_status }}</td><td>{{ file.scan_status }}</td>
            <td><button type="button" :data-test="`download-${file.id}`" :disabled="downloadingId !== null" @click="download(file)">Download</button></td>
          </tr></tbody>
        </table>
      </section>
    </template>
  </section>
</template>
