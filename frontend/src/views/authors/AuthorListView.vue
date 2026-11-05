<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  createAuthor,
  createInstitution,
  deleteAuthor,
  deleteInstitution,
  listAuthors,
  listInstitutions,
  updateInstitution,
  type AuthorCreate,
  type AuthorListQuery,
  type AuthorResponse,
  type AuthorUpdate,
  type InstitutionCreate,
  type InstitutionListQuery,
  type InstitutionSummaryResponse,
  type InstitutionUpdate,
  type SortOrder,
} from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import AuthorForm from '../../components/AuthorForm.vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const activeTab = ref<'authors' | 'institutions'>('authors')

const authors = ref<AuthorResponse[]>([])
const authorTotal = ref(0)
const authorLoading = ref(false)
const authorError = ref('')
const authorQuery = reactive({
  page: 1,
  page_size: 20,
  name: '',
  sort: 'display_name' as NonNullable<AuthorListQuery['sort']>,
  order: 'asc' as SortOrder,
})
const showAuthorForm = ref(false)
const authorBusy = ref(false)
const deletingAuthorId = ref<string | null>(null)
const authorDeleteConfirmed = ref(false)
let authorSequence = 0

const institutions = ref<InstitutionSummaryResponse[]>([])
const institutionTotal = ref(0)
const institutionLoading = ref(false)
const institutionError = ref('')
const institutionQuery = reactive({
  page: 1,
  page_size: 20,
  name: '',
  sort: 'name' as NonNullable<InstitutionListQuery['sort']>,
  order: 'asc' as SortOrder,
})
const showInstitutionForm = ref(false)
const editingInstitutionId = ref<string | null>(null)
const institutionBusy = ref(false)
const institutionForm = reactive({
  name: '',
  institution_type: '',
  website_url: '',
  country_code: '',
  city: '',
})
const deletingInstitutionId = ref<string | null>(null)
const institutionDeleteConfirmed = ref(false)
let institutionSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

async function loadAuthors(): Promise<void> {
  const sequence = ++authorSequence
  authorLoading.value = true
  authorError.value = ''
  try {
    const page = await listAuthors({
      ...authorQuery,
      name: authorQuery.name.trim() || undefined,
    })
    if (sequence !== authorSequence) return
    authors.value = page.items
    authorTotal.value = page.total
  } catch (error) {
    if (sequence !== authorSequence) return
    authors.value = []
    authorTotal.value = 0
    authorError.value = safeError(error, 'Unable to load authors.')
  } finally {
    if (sequence === authorSequence) authorLoading.value = false
  }
}

function authorPage(page: number): void {
  if (authorLoading.value || page < 1 || (page - 1) * authorQuery.page_size >= authorTotal.value) return
  authorQuery.page = page
  void loadAuthors()
}

function authorSortChanged(): void {
  authorQuery.page = 1
  void loadAuthors()
}

async function saveAuthor(payload: AuthorCreate | AuthorUpdate): Promise<void> {
  if (authorBusy.value) return
  authorBusy.value = true
  authorError.value = ''
  try {
    await createAuthor(payload as AuthorCreate)
    showAuthorForm.value = false
    await loadAuthors()
  } catch (error) {
    authorError.value = safeError(error, 'Unable to create the author.')
  } finally {
    authorBusy.value = false
  }
}

function requestAuthorDelete(authorId: string): void {
  deletingAuthorId.value = authorId
  authorDeleteConfirmed.value = false
  authorError.value = ''
}

async function confirmAuthorDelete(): Promise<void> {
  if (!deletingAuthorId.value || authorBusy.value) return
  if (!authorDeleteConfirmed.value) {
    authorError.value = 'Confirm author soft deletion before continuing.'
    return
  }
  authorBusy.value = true
  authorError.value = ''
  try {
    await deleteAuthor(deletingAuthorId.value)
    deletingAuthorId.value = null
    await loadAuthors()
  } catch (error) {
    authorError.value = safeError(error, 'Unable to delete the author.')
  } finally {
    authorBusy.value = false
  }
}

async function loadInstitutions(): Promise<void> {
  const sequence = ++institutionSequence
  institutionLoading.value = true
  institutionError.value = ''
  try {
    const page = await listInstitutions({
      ...institutionQuery,
      name: institutionQuery.name.trim() || undefined,
    })
    if (sequence !== institutionSequence) return
    institutions.value = page.items
    institutionTotal.value = page.total
  } catch (error) {
    if (sequence !== institutionSequence) return
    institutions.value = []
    institutionTotal.value = 0
    institutionError.value = safeError(error, 'Unable to load institutions.')
  } finally {
    if (sequence === institutionSequence) institutionLoading.value = false
  }
}

function institutionPage(page: number): void {
  if (institutionLoading.value || page < 1 || (page - 1) * institutionQuery.page_size >= institutionTotal.value) return
  institutionQuery.page = page
  void loadInstitutions()
}

function institutionSortChanged(): void {
  institutionQuery.page = 1
  void loadInstitutions()
}

function selectTab(tab: 'authors' | 'institutions'): void {
  activeTab.value = tab
  if (tab === 'institutions') void loadInstitutions()
}

function openInstitutionForm(institution?: InstitutionSummaryResponse): void {
  editingInstitutionId.value = institution?.id ?? null
  Object.assign(institutionForm, {
    name: institution?.name ?? '',
    institution_type: institution?.institution_type ?? '',
    website_url: institution?.website_url ?? '',
    country_code: institution?.country_code ?? '',
    city: institution?.city ?? '',
  })
  showInstitutionForm.value = true
  institutionError.value = ''
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

async function saveInstitution(): Promise<void> {
  if (institutionBusy.value) return
  institutionError.value = ''
  if (!institutionForm.name.trim()) {
    institutionError.value = 'Institution name is required.'
    return
  }
  const fields = {
    institution_type: nullable(institutionForm.institution_type),
    website_url: nullable(institutionForm.website_url),
    country_code: nullable(institutionForm.country_code)?.toUpperCase() ?? null,
    city: nullable(institutionForm.city),
  }
  institutionBusy.value = true
  try {
    if (editingInstitutionId.value) {
      const payload: InstitutionUpdate = { name: institutionForm.name.trim(), ...fields }
      await updateInstitution(editingInstitutionId.value, payload)
    } else {
      const payload: InstitutionCreate = { name: institutionForm.name.trim(), ...fields }
      await createInstitution(payload)
    }
    showInstitutionForm.value = false
    editingInstitutionId.value = null
    await loadInstitutions()
  } catch (error) {
    institutionError.value = safeError(error, 'Unable to save the institution.')
  } finally {
    institutionBusy.value = false
  }
}

function requestInstitutionDelete(institutionId: string): void {
  deletingInstitutionId.value = institutionId
  institutionDeleteConfirmed.value = false
  institutionError.value = ''
}

async function confirmInstitutionDelete(): Promise<void> {
  if (!deletingInstitutionId.value || institutionBusy.value) return
  if (!institutionDeleteConfirmed.value) {
    institutionError.value = 'Confirm institution soft deletion before continuing.'
    return
  }
  institutionBusy.value = true
  institutionError.value = ''
  try {
    await deleteInstitution(deletingInstitutionId.value)
    deletingInstitutionId.value = null
    await loadInstitutions()
  } catch (error) {
    institutionError.value = safeError(error, 'Unable to delete the institution.')
  } finally {
    institutionBusy.value = false
  }
}

onMounted(() => void loadAuthors())
</script>

<template>
  <section class="management-page" aria-labelledby="author-list-title">
    <h1 id="author-list-title">Authors and institutions</h1>
    <div class="tabs" role="tablist" aria-label="Author resources">
      <button type="button" role="tab" :aria-selected="activeTab === 'authors'" @click="selectTab('authors')">Authors</button>
      <button type="button" role="tab" data-test="institutions-tab" :aria-selected="activeTab === 'institutions'" @click="selectTab('institutions')">Institutions</button>
    </div>

    <section v-if="activeTab === 'authors'" aria-label="Author management">
      <div class="toolbar">
        <label>Search name<input v-model="authorQuery.name" data-test="author-name-filter" @change="authorQuery.page = 1; loadAuthors()"></label>
        <label>Sort<select v-model="authorQuery.sort" data-test="author-sort" @change="authorSortChanged"><option value="display_name">Display name</option><option value="created_at">Created at</option><option value="updated_at">Updated at</option></select></label>
        <label>Order<select v-model="authorQuery.order" @change="authorSortChanged"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-author" @click="showAuthorForm = true">Add author</button>
      </div>
      <p v-if="authorError" class="form-error" role="alert">{{ authorError }}</p>
      <AuthorForm v-if="showAuthorForm" data-test="author-create-form" :submitting="authorBusy" @submit="saveAuthor" @cancel="showAuthorForm = false" />
      <p v-if="authorLoading">Loading authors…</p>
      <p v-else-if="authors.length === 0">No authors found.</p>
      <table v-else>
        <thead><tr><th>Display name</th><th>ORCID</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody><tr v-for="author in authors" :key="author.id">
          <td>{{ author.display_name }}</td><td>{{ author.orcid ?? '—' }}</td><td>{{ author.status }}</td>
          <td class="table-actions">
            <RouterLink :to="`/authors/${author.id}`">View</RouterLink>
            <RouterLink :to="`/authors/${author.id}/authorizations`">Authorizations</RouterLink>
            <button v-if="isAdmin" type="button" :data-test="`delete-author-${author.id}`" @click="requestAuthorDelete(author.id)">Delete</button>
          </td>
        </tr></tbody>
      </table>
      <section v-if="deletingAuthorId" class="confirmation-panel" aria-label="Confirm author deletion">
        <p>Soft-delete this author? Existing history is retained, but the profile leaves active lists.</p>
        <label class="confirmation-control"><input v-model="authorDeleteConfirmed" data-test="author-delete-confirm" type="checkbox"> I confirm this author soft deletion.</label>
        <button type="button" :data-test="`confirm-delete-author-${deletingAuthorId}`" @click="confirmAuthorDelete">Confirm deletion</button>
        <button type="button" @click="deletingAuthorId = null">Cancel</button>
      </section>
      <nav class="pagination" aria-label="Author pages">
        <button type="button" :disabled="authorQuery.page === 1 || authorLoading" @click="authorPage(authorQuery.page - 1)">Previous</button>
        <span>Page {{ authorQuery.page }} · {{ authorTotal }} total</span>
        <button type="button" data-test="next-authors" :disabled="authorQuery.page * authorQuery.page_size >= authorTotal || authorLoading" @click="authorPage(authorQuery.page + 1)">Next</button>
      </nav>
    </section>

    <section v-else aria-label="Institution management">
      <div class="toolbar">
        <label>Search name<input v-model="institutionQuery.name" @change="institutionQuery.page = 1; loadInstitutions()"></label>
        <label>Sort<select v-model="institutionQuery.sort" @change="institutionSortChanged"><option value="name">Name</option><option value="created_at">Created at</option><option value="updated_at">Updated at</option></select></label>
        <label>Order<select v-model="institutionQuery.order" @change="institutionSortChanged"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-institution" @click="openInstitutionForm()">Add institution</button>
      </div>
      <p v-if="institutionError" class="form-error" role="alert">{{ institutionError }}</p>
      <form v-if="showInstitutionForm" data-test="institution-form" class="stacked-form" novalidate @submit.prevent="saveInstitution">
        <h2>{{ editingInstitutionId ? 'Edit institution' : 'Add institution' }}</h2>
        <div class="form-grid">
          <label>Name<input v-model="institutionForm.name" data-test="institution-name" required maxlength="255"></label>
          <label>Type<input v-model="institutionForm.institution_type" maxlength="32"></label>
          <label>Website<input v-model="institutionForm.website_url" data-test="institution-website" type="url"></label>
          <label>Country code<input v-model="institutionForm.country_code" maxlength="2" placeholder="CN"></label>
          <label>City<input v-model="institutionForm.city" maxlength="128"></label>
        </div>
        <button type="submit" :disabled="institutionBusy">Save institution</button>
        <button type="button" @click="showInstitutionForm = false">Cancel</button>
      </form>
      <p v-if="institutionLoading">Loading institutions…</p>
      <p v-else-if="institutions.length === 0">No institutions found.</p>
      <table v-else>
        <thead><tr><th>Name</th><th>Type</th><th>City</th><th>Country</th><th>Website</th><th v-if="isAdmin">Actions</th></tr></thead>
        <tbody><tr v-for="institution in institutions" :key="institution.id">
          <td>{{ institution.name }}</td><td>{{ institution.institution_type ?? '—' }}</td><td>{{ institution.city ?? '—' }}</td><td>{{ institution.country_code ?? '—' }}</td>
          <td><a v-if="institution.website_url" :href="institution.website_url" rel="noopener noreferrer" target="_blank">Website</a><span v-else>—</span></td>
          <td v-if="isAdmin"><button type="button" :data-test="`edit-institution-${institution.id}`" @click="openInstitutionForm(institution)">Edit</button><button type="button" :data-test="`delete-institution-${institution.id}`" @click="requestInstitutionDelete(institution.id)">Delete</button></td>
        </tr></tbody>
      </table>
      <section v-if="deletingInstitutionId" class="confirmation-panel" aria-label="Confirm institution deletion">
        <p>Soft-delete this institution? Active author links must be managed separately.</p>
        <label class="confirmation-control"><input v-model="institutionDeleteConfirmed" data-test="institution-delete-confirm" type="checkbox"> I confirm this institution soft deletion.</label>
        <button type="button" :data-test="`confirm-delete-institution-${deletingInstitutionId}`" @click="confirmInstitutionDelete">Confirm deletion</button>
        <button type="button" @click="deletingInstitutionId = null">Cancel</button>
      </section>
      <nav class="pagination" aria-label="Institution pages">
        <button type="button" :disabled="institutionQuery.page === 1 || institutionLoading" @click="institutionPage(institutionQuery.page - 1)">Previous</button>
        <span>Page {{ institutionQuery.page }} · {{ institutionTotal }} total</span>
        <button type="button" :disabled="institutionQuery.page * institutionQuery.page_size >= institutionTotal || institutionLoading" @click="institutionPage(institutionQuery.page + 1)">Next</button>
      </nav>
    </section>
  </section>
</template>
