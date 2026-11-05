<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listAuthors, type AuthorResponse, type SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import {
  createManuscript,
  listManuscripts,
  type Manuscript,
  type ManuscriptAuthor,
  type ManuscriptAuthorsUpdate,
  type ManuscriptListQuery,
  type ManuscriptStatus,
} from '../../api/manuscripts'
import { fetchAllPages } from '../../api/pagination'
import AuthorshipEditor from '../../components/AuthorshipEditor.vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const canCreate = computed(() => auth.user?.roles.some(
  (role) => role === 'system_admin' || role === 'submission_operator',
) ?? false)

const manuscripts = ref<Manuscript[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const query = reactive({
  page: 1,
  page_size: 20,
  status: '' as ManuscriptStatus | '',
  sort: 'created_at' as NonNullable<ManuscriptListQuery['sort']>,
  order: 'desc' as SortOrder,
})
let loadSequence = 0

const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const authorOptions = ref<AuthorResponse[]>([])
const authorOptionsLoaded = ref(false)
const ownerAuthorId = ref('')
const createAuthors = ref<ManuscriptAuthor[]>([])
const metadata = reactive({
  title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: 'en',
  funding_statement: '', conflict_of_interest_statement: '', ethics_statement: '',
  data_availability_statement: '', notes: '',
})

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await listManuscripts({
      ...query,
      status: query.status || undefined,
    })
    if (sequence !== loadSequence) return
    manuscripts.value = result.items
    total.value = result.total
  } catch (error) {
    if (sequence !== loadSequence) return
    manuscripts.value = []
    total.value = 0
    errorMessage.value = safeError(error, 'Unable to load manuscripts.')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function applyFilters(): void {
  query.page = 1
  void load()
}

function changePage(page: number): void {
  if (loading.value || page < 1 || (page - 1) * query.page_size >= total.value) return
  query.page = page
  void load()
}

async function openCreate(): Promise<void> {
  if (!canCreate.value) return
  showCreate.value = true
  createError.value = ''
  if (authorOptionsLoaded.value) return
  try {
    const result = await fetchAllPages((page, pageSize) => listAuthors({
      page, page_size: pageSize, sort: 'display_name', order: 'asc',
    }))
    authorOptions.value = result.items
    authorOptionsLoaded.value = true
  } catch (error) {
    createError.value = safeError(error, 'Unable to load authorized owner choices.')
  }
}

function ownerChanged(): void {
  const owner = authorOptions.value.find((author) => author.id === ownerAuthorId.value)
  createAuthors.value = owner ? [{
    author_id: owner.id,
    display_name: owner.display_name,
    position: 1,
    is_corresponding: true,
  }] : []
}

function nullable(value: string): string | null {
  return value.trim() || null
}

async function saveCreate(authorship: ManuscriptAuthorsUpdate): Promise<void> {
  if (creating.value || !canCreate.value) return
  createError.value = ''
  if (!ownerAuthorId.value || !metadata.title.trim() || !metadata.abstract.trim()
    || !metadata.article_type.trim() || !metadata.language.trim()) {
    createError.value = 'Owner, title, abstract, article type, and language are required.'
    return
  }
  creating.value = true
  try {
    await createManuscript({
      owner_author_id: ownerAuthorId.value,
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
      authors: authorship.authors,
    })
    showCreate.value = false
    ownerAuthorId.value = ''
    createAuthors.value = []
    Object.assign(metadata, {
      title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: 'en',
      funding_statement: '', conflict_of_interest_statement: '', ethics_statement: '',
      data_availability_statement: '', notes: '',
    })
    await load()
  } catch (error) {
    createError.value = safeError(error, 'Unable to create the manuscript.')
  } finally {
    creating.value = false
  }
}

function ownerName(manuscript: Manuscript): string {
  return manuscript.authors.find((author) => author.author_id === manuscript.owner_author_id)?.display_name ?? '—'
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="manuscript-list-title">
    <h1 id="manuscript-list-title">Manuscripts</h1>
    <div class="toolbar">
      <label>Status
        <select v-model="query.status" data-test="status-filter">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
      </label>
      <label>Sort
        <select v-model="query.sort" data-test="manuscript-sort" @change="applyFilters">
          <option value="created_at">Created at</option>
          <option value="updated_at">Updated at</option>
          <option value="title">Title</option>
        </select>
      </label>
      <label>Order
        <select v-model="query.order" @change="applyFilters">
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
      <button type="button" data-test="apply-filters" @click="applyFilters">Apply filters</button>
      <button v-if="canCreate" type="button" data-test="add-manuscript" @click="openCreate">New manuscript</button>
    </div>

    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <section v-if="showCreate" aria-labelledby="create-manuscript-title">
      <h2 id="create-manuscript-title">Create manuscript</h2>
      <div class="stacked-form">
        <label>Owner author
          <select v-model="ownerAuthorId" data-test="owner-author" required @change="ownerChanged">
            <option value="">Select an authorized owner</option>
            <option v-for="author in authorOptions" :key="author.id" :value="author.id">{{ author.display_name }}</option>
          </select>
        </label>
        <div class="form-grid">
          <label>Title<input v-model="metadata.title" data-test="title" maxlength="1000" required></label>
          <label>Article type<input v-model="metadata.article_type" data-test="article-type" maxlength="100" required></label>
          <label>Language<input v-model="metadata.language" data-test="language" maxlength="32" required></label>
          <label>Subject field<input v-model="metadata.subject_field" maxlength="255"></label>
          <label>Keywords (comma separated)<input v-model="metadata.keywords" data-test="keywords"></label>
        </div>
        <label>Abstract<textarea v-model="metadata.abstract" data-test="abstract" rows="6" required></textarea></label>
        <label>Funding statement<textarea v-model="metadata.funding_statement" rows="3"></textarea></label>
        <label>Conflict of interest statement<textarea v-model="metadata.conflict_of_interest_statement" rows="3"></textarea></label>
        <label>Ethics statement<textarea v-model="metadata.ethics_statement" rows="3"></textarea></label>
        <label>Data availability statement<textarea v-model="metadata.data_availability_statement" rows="3"></textarea></label>
        <label>Notes<textarea v-model="metadata.notes" rows="3"></textarea></label>
      </div>
      <AuthorshipEditor
        v-if="ownerAuthorId"
        data-test="create-authorship-form"
        :model-value="createAuthors"
        :owner-author-id="ownerAuthorId"
        :available-authors="authorOptions"
        :submitting="creating"
        @submit="saveCreate"
      />
      <p v-if="createError" class="form-error" role="alert">{{ createError }}</p>
      <button type="button" :disabled="creating" @click="showCreate = false">Cancel</button>
    </section>

    <p v-if="loading">Loading manuscripts…</p>
    <p v-else-if="!errorMessage && manuscripts.length === 0">No manuscripts found.</p>
    <table v-else>
      <thead><tr><th>Internal number</th><th>Title</th><th>Owner</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
      <tbody><tr v-for="manuscript in manuscripts" :key="manuscript.id">
        <td>{{ manuscript.internal_number }}</td>
        <td>{{ manuscript.title }}</td>
        <td>{{ ownerName(manuscript) }}</td>
        <td>{{ manuscript.status }}</td>
        <td><time :datetime="manuscript.updated_at">{{ manuscript.updated_at }}</time></td>
        <td><RouterLink :to="`/manuscripts/${manuscript.id}`">Open workspace</RouterLink></td>
      </tr></tbody>
    </table>
    <nav class="pagination" aria-label="Manuscript pages">
      <button type="button" :disabled="query.page === 1 || loading" @click="changePage(query.page - 1)">Previous</button>
      <span>Page {{ query.page }} · {{ total }} total</span>
      <button type="button" data-test="next-manuscripts" :disabled="query.page * query.page_size >= total || loading" @click="changePage(query.page + 1)">Next</button>
    </nav>
  </section>
</template>
