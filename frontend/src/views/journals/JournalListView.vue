<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createJournal,
  createPlatform,
  createPublisher,
  deleteJournal,
  deletePlatform,
  deletePublisher,
  listJournals,
  listPlatforms,
  listPublishers,
  updateJournal,
  updatePlatform,
  updatePublisher,
  type JournalListQuery,
  type JournalPlatformResponse,
  type JournalResponse,
  type PlatformListQuery,
  type PublisherListQuery,
  type PublisherResponse,
} from '../../api/journals'
import type { SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const activeTab = ref<'publishers' | 'platforms' | 'journals'>('publishers')
const errorMessage = ref('')
const busy = ref(false)

const publishers = ref<PublisherResponse[]>([])
const publisherTotal = ref(0)
const publisherLoading = ref(false)
const publisherQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'name' as NonNullable<PublisherListQuery['sort']>, order: 'asc' as SortOrder })
const showPublisherForm = ref(false)
const editingPublisherId = ref<string | null>(null)
const publisherForm = reactive({ name: '', website_url: '', notes: '' })
let publisherSequence = 0

const platforms = ref<JournalPlatformResponse[]>([])
const platformTotal = ref(0)
const platformLoading = ref(false)
const platformQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'code' as NonNullable<PlatformListQuery['sort']>, order: 'asc' as SortOrder })
const showPlatformForm = ref(false)
const editingPlatformId = ref<string | null>(null)
const platformForm = reactive({ code: '', name: '', description: '', status: 'active' as 'active' | 'needs_review' | 'disabled' })
let platformSequence = 0

const journals = ref<JournalResponse[]>([])
const journalTotal = ref(0)
const journalLoading = ref(false)
const journalQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'name' as NonNullable<JournalListQuery['sort']>, order: 'asc' as SortOrder })
const showJournalForm = ref(false)
const editingJournalId = ref<string | null>(null)
const publisherOptions = ref<PublisherResponse[]>([])
const platformOptions = ref<JournalPlatformResponse[]>([])
const journalForm = reactive({
  publisher_id: '',
  platform_id: '',
  name: '',
  issn: '',
  eissn: '',
  website_url: '',
  submission_url: '',
  author_guidelines_url: '',
  subject_categories: '',
  article_types: '',
  requirements: [] as Array<{ key: string; value: string; scope: string; source_url: string; verified_at: string }>,
  requirements_source_url: '',
  requirements_verified_at: '',
  status: 'active',
  notes: '',
})
let journalSequence = 0

const deleteTarget = ref<{ kind: 'publisher' | 'platform' | 'journal'; id: string } | null>(null)
const deleteConfirmed = ref(false)

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

async function loadPublishers(): Promise<void> {
  const sequence = ++publisherSequence
  publisherLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listPublishers({ ...publisherQuery, name: publisherQuery.name.trim() || undefined })
    if (sequence !== publisherSequence) return
    publishers.value = result.items
    publisherTotal.value = result.total
  } catch (error) {
    if (sequence !== publisherSequence) return
    publishers.value = []
    publisherTotal.value = 0
    errorMessage.value = safeError(error, 'Unable to load publishers.')
  } finally {
    if (sequence === publisherSequence) publisherLoading.value = false
  }
}

function publisherPage(page: number): void {
  if (publisherLoading.value || page < 1 || (page - 1) * publisherQuery.page_size >= publisherTotal.value) return
  publisherQuery.page = page
  void loadPublishers()
}

function publisherSortChanged(): void {
  publisherQuery.page = 1
  void loadPublishers()
}

function openPublisherForm(publisher?: PublisherResponse): void {
  editingPublisherId.value = publisher?.id ?? null
  Object.assign(publisherForm, { name: publisher?.name ?? '', website_url: publisher?.website_url ?? '', notes: publisher?.notes ?? '' })
  showPublisherForm.value = true
  errorMessage.value = ''
}

async function savePublisher(): Promise<void> {
  if (busy.value) return
  if (!publisherForm.name.trim()) {
    errorMessage.value = 'Publisher name is required.'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const payload = { name: publisherForm.name.trim(), website_url: nullable(publisherForm.website_url), notes: nullable(publisherForm.notes) }
  try {
    if (editingPublisherId.value) await updatePublisher(editingPublisherId.value, payload)
    else await createPublisher(payload)
    showPublisherForm.value = false
    editingPublisherId.value = null
    await loadPublishers()
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to save the publisher.')
  } finally {
    busy.value = false
  }
}

async function loadPlatforms(): Promise<void> {
  const sequence = ++platformSequence
  platformLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listPlatforms({ ...platformQuery, name: platformQuery.name.trim() || undefined })
    if (sequence !== platformSequence) return
    platforms.value = result.items
    platformTotal.value = result.total
  } catch (error) {
    if (sequence !== platformSequence) return
    platforms.value = []
    platformTotal.value = 0
    errorMessage.value = safeError(error, 'Unable to load platforms.')
  } finally {
    if (sequence === platformSequence) platformLoading.value = false
  }
}

function platformPage(page: number): void {
  if (platformLoading.value || page < 1 || (page - 1) * platformQuery.page_size >= platformTotal.value) return
  platformQuery.page = page
  void loadPlatforms()
}

function platformSortChanged(): void {
  platformQuery.page = 1
  void loadPlatforms()
}

function openPlatformForm(platform?: JournalPlatformResponse): void {
  editingPlatformId.value = platform?.id ?? null
  Object.assign(platformForm, {
    code: platform?.code ?? '', name: platform?.name ?? '', description: platform?.description ?? '', status: platform?.status ?? 'active',
  })
  showPlatformForm.value = true
  errorMessage.value = ''
}

async function savePlatform(): Promise<void> {
  if (busy.value) return
  if (!platformForm.code.trim() || !platformForm.name.trim()) {
    errorMessage.value = 'Platform code and name are required.'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const payload = {
    code: platformForm.code.trim(), name: platformForm.name.trim(),
    description: platformForm.description, status: platformForm.status,
  }
  try {
    if (editingPlatformId.value) await updatePlatform(editingPlatformId.value, payload)
    else await createPlatform(payload)
    showPlatformForm.value = false
    editingPlatformId.value = null
    await loadPlatforms()
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to save the platform.')
  } finally {
    busy.value = false
  }
}

async function loadJournals(): Promise<void> {
  const sequence = ++journalSequence
  journalLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listJournals({ ...journalQuery, name: journalQuery.name.trim() || undefined })
    if (sequence !== journalSequence) return
    journals.value = result.items
    journalTotal.value = result.total
  } catch (error) {
    if (sequence !== journalSequence) return
    journals.value = []
    journalTotal.value = 0
    errorMessage.value = safeError(error, 'Unable to load journals.')
  } finally {
    if (sequence === journalSequence) journalLoading.value = false
  }
}

function journalPage(page: number): void {
  if (journalLoading.value || page < 1 || (page - 1) * journalQuery.page_size >= journalTotal.value) return
  journalQuery.page = page
  void loadJournals()
}

function journalSortChanged(): void {
  journalQuery.page = 1
  void loadJournals()
}

function toInputDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

async function openJournalForm(journal?: JournalResponse): Promise<void> {
  editingJournalId.value = journal?.id ?? null
  Object.assign(journalForm, {
    publisher_id: journal?.publisher_id ?? '', platform_id: journal?.platform_id ?? '', name: journal?.name ?? '',
    issn: journal?.issn ?? '', eissn: journal?.eissn ?? '', website_url: journal?.website_url ?? '',
    submission_url: journal?.submission_url ?? '', author_guidelines_url: journal?.author_guidelines_url ?? '',
    subject_categories: journal?.subject_categories.join(', ') ?? '', article_types: journal?.article_types.join(', ') ?? '',
    requirements: journal?.requirements.map((requirement) => ({
      key: requirement.key, value: String(requirement.value), scope: requirement.scope,
      source_url: requirement.source_url, verified_at: toInputDate(requirement.verified_at),
    })) ?? [],
    requirements_source_url: journal?.requirements_source_url ?? '',
    requirements_verified_at: journal?.requirements_verified_at ? toInputDate(journal.requirements_verified_at) : '',
    status: journal?.status ?? 'active', notes: journal?.notes ?? '',
  })
  showJournalForm.value = true
  errorMessage.value = ''
  try {
    const [publisherPage, platformPage] = await Promise.all([
      listPublishers({ page: 1, page_size: 100, sort: 'name', order: 'asc' }),
      listPlatforms({ page: 1, page_size: 100, sort: 'name', order: 'asc' }),
    ])
    publisherOptions.value = publisherPage.items
    platformOptions.value = platformPage.items
  } catch (error) {
    publisherOptions.value = []
    platformOptions.value = []
    errorMessage.value = safeError(error, 'Unable to load journal relationship choices.')
  }
}

function addRequirement(): void {
  journalForm.requirements.push({ key: '', value: '', scope: '', source_url: '', verified_at: '' })
}

function isHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && Boolean(url.hostname) && !url.username && !url.password
  } catch {
    return false
  }
}

function isoDate(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function commaSeparated(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

async function saveJournal(): Promise<void> {
  if (busy.value) return
  errorMessage.value = ''
  if (!journalForm.publisher_id || !journalForm.name.trim()) {
    errorMessage.value = 'Publisher and journal name are required.'
    return
  }
  for (const requirement of journalForm.requirements) {
    if (!requirement.key.trim() || !requirement.value.trim() || !requirement.scope.trim() || !requirement.source_url.trim() || !requirement.verified_at) {
      errorMessage.value = 'Requirement key, value, scope, HTTPS source URL, and verification time are required for every row.'
      return
    }
    if (!isHttpsUrl(requirement.source_url.trim())) {
      errorMessage.value = 'Every requirement source URL must use HTTPS without user information.'
      return
    }
    if (!isoDate(requirement.verified_at)) {
      errorMessage.value = 'Every requirement verification time must be a finite date.'
      return
    }
  }
  if (journalForm.requirements_verified_at && !isoDate(journalForm.requirements_verified_at)) {
    errorMessage.value = 'Overall requirements verification time must be a finite date.'
    return
  }
  const payload = {
    publisher_id: journalForm.publisher_id,
    platform_id: journalForm.platform_id || null,
    name: journalForm.name.trim(),
    issn: nullable(journalForm.issn), eissn: nullable(journalForm.eissn),
    website_url: nullable(journalForm.website_url), submission_url: nullable(journalForm.submission_url),
    author_guidelines_url: nullable(journalForm.author_guidelines_url),
    subject_categories: commaSeparated(journalForm.subject_categories),
    article_types: commaSeparated(journalForm.article_types),
    requirements: journalForm.requirements.map((requirement) => ({
      key: requirement.key.trim(), value: requirement.value.trim(), scope: requirement.scope.trim(),
      source_url: requirement.source_url.trim(), verified_at: isoDate(requirement.verified_at) as string,
    })),
    requirements_source_url: nullable(journalForm.requirements_source_url),
    requirements_verified_at: journalForm.requirements_verified_at ? isoDate(journalForm.requirements_verified_at) : null,
    status: journalForm.status.trim() || 'active', notes: nullable(journalForm.notes),
  }
  busy.value = true
  try {
    if (editingJournalId.value) await updateJournal(editingJournalId.value, payload)
    else await createJournal(payload)
    showJournalForm.value = false
    editingJournalId.value = null
    await loadJournals()
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to save the journal.')
  } finally {
    busy.value = false
  }
}

function requestDelete(kind: 'publisher' | 'platform' | 'journal', id: string): void {
  deleteTarget.value = { kind, id }
  deleteConfirmed.value = false
  errorMessage.value = ''
}

async function confirmDelete(): Promise<void> {
  if (!deleteTarget.value || busy.value) return
  if (!deleteConfirmed.value) {
    errorMessage.value = 'Confirm soft deletion before continuing.'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const { kind, id } = deleteTarget.value
  try {
    if (kind === 'publisher') {
      await deletePublisher(id)
      await loadPublishers()
    } else if (kind === 'platform') {
      await deletePlatform(id)
      await loadPlatforms()
    } else {
      await deleteJournal(id)
      await loadJournals()
    }
    deleteTarget.value = null
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to delete the resource.')
  } finally {
    busy.value = false
  }
}

function selectTab(tab: 'publishers' | 'platforms' | 'journals'): void {
  activeTab.value = tab
  deleteTarget.value = null
  errorMessage.value = ''
  if (tab === 'publishers') void loadPublishers()
  else if (tab === 'platforms') void loadPlatforms()
  else void loadJournals()
}

function formatIssn(value: string | null | undefined): string {
  if (!value) return '—'
  return /^[0-9X]{8}$/i.test(value) ? `${value.slice(0, 4)}-${value.slice(4)}` : value
}

onMounted(() => void loadPublishers())
</script>

<template>
  <section class="management-page" aria-labelledby="journal-resources-title">
    <h1 id="journal-resources-title">Publishers, platforms, and journals</h1>
    <div class="tabs" role="tablist" aria-label="Journal resources">
      <button type="button" role="tab" :aria-selected="activeTab === 'publishers'" @click="selectTab('publishers')">Publishers</button>
      <button type="button" role="tab" data-test="platforms-tab" :aria-selected="activeTab === 'platforms'" @click="selectTab('platforms')">Platforms</button>
      <button type="button" role="tab" data-test="journals-tab" :aria-selected="activeTab === 'journals'" @click="selectTab('journals')">Journals</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <section v-if="activeTab === 'publishers'" aria-label="Publisher management">
      <div class="toolbar">
        <label>Search name<input v-model="publisherQuery.name" @change="publisherQuery.page = 1; loadPublishers()"></label>
        <label>Sort<select v-model="publisherQuery.sort" data-test="publisher-sort" @change="publisherSortChanged"><option value="name">Name</option><option value="created_at">Created at</option><option value="updated_at">Updated at</option></select></label>
        <label>Order<select v-model="publisherQuery.order" @change="publisherSortChanged"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-publisher" @click="openPublisherForm()">Add publisher</button>
      </div>
      <form v-if="showPublisherForm" data-test="publisher-form" class="stacked-form" novalidate @submit.prevent="savePublisher">
        <h2>{{ editingPublisherId ? 'Edit publisher' : 'Add publisher' }}</h2>
        <label>Name<input v-model="publisherForm.name" data-test="publisher-name" required maxlength="255"></label>
        <label>Website<input v-model="publisherForm.website_url" type="url"></label>
        <label>Notes<textarea v-model="publisherForm.notes" rows="3"></textarea></label>
        <button type="submit" :disabled="busy">Save publisher</button><button type="button" @click="showPublisherForm = false">Cancel</button>
      </form>
      <p v-if="publisherLoading">Loading publishers…</p><p v-else-if="publishers.length === 0">No publishers found.</p>
      <table v-else>
        <thead><tr><th>Name</th><th>Website</th><th v-if="isAdmin">Actions</th></tr></thead>
        <tbody><tr v-for="publisher in publishers" :key="publisher.id"><td>{{ publisher.name }}</td><td><a v-if="publisher.website_url" :href="publisher.website_url" target="_blank" rel="noopener noreferrer">Website</a><span v-else>—</span></td><td v-if="isAdmin"><button type="button" :data-test="`edit-publisher-${publisher.id}`" @click="openPublisherForm(publisher)">Edit</button><button type="button" :data-test="`delete-publisher-${publisher.id}`" @click="requestDelete('publisher', publisher.id)">Delete</button></td></tr></tbody>
      </table>
      <nav class="pagination" aria-label="Publisher pages"><button type="button" :disabled="publisherQuery.page === 1 || publisherLoading" @click="publisherPage(publisherQuery.page - 1)">Previous</button><span>Page {{ publisherQuery.page }} · {{ publisherTotal }} total</span><button type="button" data-test="next-publishers" :disabled="publisherQuery.page * publisherQuery.page_size >= publisherTotal || publisherLoading" @click="publisherPage(publisherQuery.page + 1)">Next</button></nav>
    </section>

    <section v-else-if="activeTab === 'platforms'" aria-label="Platform management">
      <div class="toolbar">
        <label>Search name<input v-model="platformQuery.name" @change="platformQuery.page = 1; loadPlatforms()"></label>
        <label>Sort<select v-model="platformQuery.sort" data-test="platform-sort" @change="platformSortChanged"><option value="code">Code</option><option value="name">Name</option><option value="created_at">Created at</option><option value="updated_at">Updated at</option></select></label>
        <label>Order<select v-model="platformQuery.order" @change="platformSortChanged"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-platform" @click="openPlatformForm()">Add platform</button>
      </div>
      <form v-if="showPlatformForm" data-test="platform-form" class="stacked-form" novalidate @submit.prevent="savePlatform">
        <h2>{{ editingPlatformId ? 'Edit platform' : 'Add platform' }}</h2>
        <label>Code<input v-model="platformForm.code" data-test="platform-code" required maxlength="64"></label>
        <label>Name<input v-model="platformForm.name" data-test="platform-name" required maxlength="255"></label>
        <label>Description<textarea v-model="platformForm.description" rows="3"></textarea></label>
        <label>Status<select v-model="platformForm.status"><option value="active">Active</option><option value="needs_review">Needs review</option><option value="disabled">Disabled</option></select></label>
        <button type="submit" :disabled="busy">Save platform</button><button type="button" @click="showPlatformForm = false">Cancel</button>
      </form>
      <p v-if="platformLoading">Loading platforms…</p><p v-else-if="platforms.length === 0">No platforms found.</p>
      <table v-else>
        <thead><tr><th>Code</th><th>Name</th><th>Status</th><th v-if="isAdmin">Actions</th></tr></thead>
        <tbody><tr v-for="platform in platforms" :key="platform.id"><td>{{ platform.code }}</td><td>{{ platform.name }}</td><td>{{ platform.status }}</td><td v-if="isAdmin"><button type="button" :data-test="`edit-platform-${platform.id}`" @click="openPlatformForm(platform)">Edit</button><button type="button" :data-test="`delete-platform-${platform.id}`" @click="requestDelete('platform', platform.id)">Delete</button></td></tr></tbody>
      </table>
      <nav class="pagination" aria-label="Platform pages"><button type="button" :disabled="platformQuery.page === 1 || platformLoading" @click="platformPage(platformQuery.page - 1)">Previous</button><span>Page {{ platformQuery.page }} · {{ platformTotal }} total</span><button type="button" data-test="next-platforms" :disabled="platformQuery.page * platformQuery.page_size >= platformTotal || platformLoading" @click="platformPage(platformQuery.page + 1)">Next</button></nav>
    </section>

    <section v-else aria-label="Journal management">
      <div class="toolbar">
        <label>Search name<input v-model="journalQuery.name" @change="journalQuery.page = 1; loadJournals()"></label>
        <label>Sort<select v-model="journalQuery.sort" data-test="journal-sort" @change="journalSortChanged"><option value="name">Name</option><option value="created_at">Created at</option><option value="updated_at">Updated at</option></select></label>
        <label>Order<select v-model="journalQuery.order" @change="journalSortChanged"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-journal" @click="openJournalForm()">Add journal</button>
      </div>
      <form v-if="showJournalForm" data-test="journal-form" class="stacked-form" novalidate @submit.prevent="saveJournal">
        <h2>{{ editingJournalId ? 'Edit journal' : 'Add journal' }}</h2>
        <div class="form-grid">
          <label>Publisher<select v-model="journalForm.publisher_id" data-test="journal-publisher" required><option value="" disabled>Select a publisher</option><option v-for="option in publisherOptions" :key="option.id" :value="option.id">{{ option.name }}</option></select></label>
          <label>Platform<select v-model="journalForm.platform_id"><option value="">No platform</option><option v-for="option in platformOptions" :key="option.id" :value="option.id">{{ option.name }} ({{ option.code }})</option></select></label>
          <label>Name<input v-model="journalForm.name" data-test="journal-name" required maxlength="500"></label>
          <label>Status<input v-model="journalForm.status" required maxlength="32"></label>
          <label>ISSN<input v-model="journalForm.issn" placeholder="0378-5955"></label>
          <label>eISSN<input v-model="journalForm.eissn"></label>
          <label>Website<input v-model="journalForm.website_url" type="url"></label>
          <label>Submission URL<input v-model="journalForm.submission_url" type="url"></label>
          <label>Author guidelines URL<input v-model="journalForm.author_guidelines_url" type="url"></label>
        </div>
        <label>Subject categories (comma-separated)<input v-model="journalForm.subject_categories"></label>
        <label>Article types (comma-separated)<input v-model="journalForm.article_types"></label>
        <fieldset>
          <legend>Journal requirements</legend>
          <p>Every row needs a key, value, scope, HTTPS source URL, and verification time.</p>
          <div v-for="(requirement, index) in journalForm.requirements" :key="index" class="requirement-row">
            <div class="form-grid">
              <label>Key<input v-model="requirement.key" data-test="requirement-key" required></label>
              <label>Value<input v-model="requirement.value" data-test="requirement-value" required></label>
              <label>Scope<input v-model="requirement.scope" data-test="requirement-scope" required></label>
              <label>HTTPS source URL<input v-model="requirement.source_url" data-test="requirement-source" type="url" required></label>
              <label>Verified at<input v-model="requirement.verified_at" data-test="requirement-verified" type="datetime-local" required></label>
            </div>
            <button type="button" @click="journalForm.requirements.splice(index, 1)">Remove requirement</button>
          </div>
          <button type="button" data-test="add-requirement" @click="addRequirement">Add requirement</button>
        </fieldset>
        <label>Overall requirements source URL<input v-model="journalForm.requirements_source_url" type="url"></label>
        <label>Overall requirements verified at<input v-model="journalForm.requirements_verified_at" type="datetime-local"></label>
        <label>Notes<textarea v-model="journalForm.notes" rows="3"></textarea></label>
        <button type="submit" :disabled="busy">Save journal</button><button type="button" @click="showJournalForm = false">Cancel</button>
      </form>
      <p v-if="journalLoading">Loading journals…</p><p v-else-if="journals.length === 0">No journals found.</p>
      <table v-else>
        <thead><tr><th>Name</th><th>ISSN</th><th>eISSN</th><th>Publisher ID</th><th>Platform ID</th><th>Status</th><th>Requirements</th><th v-if="isAdmin">Actions</th></tr></thead>
        <tbody><tr v-for="journal in journals" :key="journal.id">
          <td>{{ journal.name }}</td><td>{{ formatIssn(journal.issn) }}</td><td>{{ formatIssn(journal.eissn) }}</td><td>{{ journal.publisher_id }}</td><td>{{ journal.platform_id ?? '—' }}</td><td>{{ journal.status }}</td>
          <td><details><summary>{{ journal.requirements.length }} requirements</summary><ul><li v-for="(requirement, index) in journal.requirements" :key="`${requirement.key}-${index}`">{{ requirement.key }}: {{ requirement.value }} ({{ requirement.scope }}) · <a :href="requirement.source_url" target="_blank" rel="noopener noreferrer">Source</a> · Verified {{ requirement.verified_at }}</li></ul></details></td>
          <td v-if="isAdmin"><button type="button" :data-test="`edit-journal-${journal.id}`" @click="openJournalForm(journal)">Edit</button><button type="button" :data-test="`delete-journal-${journal.id}`" @click="requestDelete('journal', journal.id)">Delete</button></td>
        </tr></tbody>
      </table>
      <nav class="pagination" aria-label="Journal pages"><button type="button" :disabled="journalQuery.page === 1 || journalLoading" @click="journalPage(journalQuery.page - 1)">Previous</button><span>Page {{ journalQuery.page }} · {{ journalTotal }} total</span><button type="button" data-test="next-journals" :disabled="journalQuery.page * journalQuery.page_size >= journalTotal || journalLoading" @click="journalPage(journalQuery.page + 1)">Next</button></nav>
    </section>

    <section v-if="deleteTarget" class="confirmation-panel" aria-label="Confirm soft deletion">
      <h2>Confirm soft deletion</h2><p>The {{ deleteTarget.kind }} will leave active lists while historical records are retained.</p>
      <label class="confirmation-control"><input v-model="deleteConfirmed" data-test="delete-confirm" type="checkbox"> I confirm this soft deletion.</label>
      <button type="button" :data-test="`confirm-delete-${deleteTarget.kind}-${deleteTarget.id}`" :disabled="busy" @click="confirmDelete">Confirm deletion</button><button type="button" @click="deleteTarget = null">Cancel</button>
    </section>
  </section>
</template>
