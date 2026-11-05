<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  createAuthorization,
  listAuthorizations,
  revokeAuthorization,
  updateAuthorization,
  PERMISSION_CODES,
  type AuthorizationListQuery,
  type AuthorizationResponse,
  type PermissionCode,
  type SortOrder,
} from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const props = withDefaults(defineProps<{ authorId?: string }>(), { authorId: '' })
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const items = ref<AuthorizationResponse[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const query = reactive({
  page: 1,
  page_size: 20,
  user_id: '',
  sort: 'created_at' as NonNullable<AuthorizationListQuery['sort']>,
  order: 'desc' as SortOrder,
})
const showForm = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = reactive({
  author_id: '',
  user_id: '',
  permissions: [] as PermissionCode[],
  valid_from: '',
  valid_to: '',
  evidence_ref: '',
  notes: '',
})
const revokingId = ref<string | null>(null)
const revokeReason = ref('')
const revokeConfirmed = ref(false)
let loadSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const page = await listAuthorizations({
      ...query,
      author_id: props.authorId || undefined,
      user_id: query.user_id.trim() || undefined,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
  } catch (error) {
    if (sequence !== loadSequence) return
    items.value = []
    total.value = 0
    errorMessage.value = safeError(error, 'Unable to load authorizations.')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function changePage(page: number): void {
  if (loading.value || page < 1 || (page - 1) * query.page_size >= total.value) return
  query.page = page
  void load()
}

function sortChanged(): void {
  query.page = 1
  void load()
}

function toInputDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

function openForm(authorization?: AuthorizationResponse): void {
  editingId.value = authorization?.id ?? null
  Object.assign(form, {
    author_id: authorization?.author_id ?? props.authorId,
    user_id: authorization?.user_id ?? '',
    permissions: authorization ? [...authorization.permissions] : [],
    valid_from: authorization ? toInputDate(authorization.valid_from) : '',
    valid_to: authorization ? toInputDate(authorization.valid_to) : '',
    evidence_ref: authorization?.evidence_ref ?? '',
    notes: authorization?.notes ?? '',
  })
  showForm.value = true
  revokingId.value = null
  errorMessage.value = ''
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

function isoDate(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

async function save(): Promise<void> {
  if (saving.value) return
  errorMessage.value = ''
  if (!form.author_id.trim() || !form.user_id.trim()) {
    errorMessage.value = 'Author ID and user ID are required.'
    return
  }
  if (form.permissions.length === 0) {
    errorMessage.value = 'Select at least one permission.'
    return
  }
  if (!form.valid_from || !form.valid_to) {
    errorMessage.value = 'Start and end times are required.'
    return
  }
  const validFrom = isoDate(form.valid_from)
  const validTo = isoDate(form.valid_to)
  if (!validFrom || !validTo) {
    errorMessage.value = 'Start and end times must be finite dates.'
    return
  }
  const startMs = new Date(validFrom).getTime()
  const endMs = new Date(validTo).getTime()
  if (endMs <= startMs) {
    errorMessage.value = 'End time must be later than start time.'
    return
  }
  if (endMs <= Date.now()) {
    errorMessage.value = 'End time must be in the future.'
    return
  }
  const common = {
    permissions: [...form.permissions].sort(),
    valid_from: validFrom,
    valid_to: validTo,
    evidence_ref: nullable(form.evidence_ref),
    notes: nullable(form.notes),
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateAuthorization(editingId.value, common)
    } else {
      await createAuthorization({
        ...common,
        author_id: form.author_id.trim(),
        user_id: form.user_id.trim(),
      })
    }
    showForm.value = false
    editingId.value = null
    await load()
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to save the authorization.')
  } finally {
    saving.value = false
  }
}

function startRevoke(authorizationId: string): void {
  revokingId.value = authorizationId
  revokeReason.value = ''
  revokeConfirmed.value = false
  showForm.value = false
  errorMessage.value = ''
}

async function confirmRevoke(): Promise<void> {
  if (!revokingId.value || saving.value) return
  if (!revokeConfirmed.value) {
    errorMessage.value = 'Confirm authorization revocation separately before continuing.'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    await revokeAuthorization(revokingId.value, { reason: nullable(revokeReason.value) })
    revokingId.value = null
    await load()
  } catch (error) {
    errorMessage.value = safeError(error, 'Unable to revoke the authorization.')
  } finally {
    saving.value = false
  }
}

watch(() => props.authorId, () => {
  query.page = 1
  showForm.value = false
  revokingId.value = null
  void load()
}, { immediate: true })
</script>

<template>
  <section class="management-page" aria-labelledby="authorization-title">
    <h1 id="authorization-title">Author authorizations</h1>
    <p>Grants are limited to the nine defined permissions and always have finite start and end times.</p>
    <div class="toolbar">
      <label>User ID<input v-model="query.user_id" @change="query.page = 1; load()"></label>
      <label>Sort<select v-model="query.sort" @change="sortChanged"><option value="created_at">Created at</option><option value="updated_at">Updated at</option><option value="valid_from">Valid from</option><option value="valid_to">Valid to</option></select></label>
      <label>Order<select v-model="query.order" @change="sortChanged"><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
      <button v-if="isAdmin" type="button" data-test="add-authorization" @click="openForm()">Add authorization</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <form v-if="showForm" data-test="authorization-form" class="stacked-form" novalidate @submit.prevent="save">
      <h2>{{ editingId ? 'Edit authorization' : 'Add authorization' }}</h2>
      <div class="form-grid">
        <label>Author ID<input v-model="form.author_id" :disabled="Boolean(editingId)" required></label>
        <label>User ID<input v-model="form.user_id" data-test="authorization-user-id" :disabled="Boolean(editingId)" required></label>
        <label>Valid from<input v-model="form.valid_from" data-test="valid-from" type="datetime-local" required></label>
        <label>Valid to<input v-model="form.valid_to" data-test="valid-to" type="datetime-local" required></label>
      </div>
      <fieldset>
        <legend>Permissions</legend>
        <label v-for="code in PERMISSION_CODES" :key="code" class="permission-option"><input v-model="form.permissions" data-test="permission-option" type="checkbox" :value="code"> {{ code }}</label>
      </fieldset>
      <label>Evidence reference<input v-model="form.evidence_ref" maxlength="1024"></label>
      <label>Notes<textarea v-model="form.notes" rows="3"></textarea></label>
      <button type="submit" :disabled="saving">Save authorization</button>
      <button type="button" @click="showForm = false">Cancel</button>
    </form>

    <section v-if="revokingId" class="confirmation-panel" aria-label="Confirm authorization revocation">
      <h2>Revoke authorization</h2>
      <p>Revocation is separate from editing and takes effect on the subject's next request.</p>
      <label>Reason<textarea v-model="revokeReason" data-test="revoke-reason" rows="3" maxlength="2000"></textarea></label>
      <label class="confirmation-control"><input v-model="revokeConfirmed" data-test="revoke-confirm" type="checkbox"> I confirm revocation of this authorization.</label>
      <button type="button" :data-test="`confirm-revoke-${revokingId}`" :disabled="saving" @click="confirmRevoke">Confirm revocation</button>
      <button type="button" @click="revokingId = null">Cancel</button>
    </section>

    <p v-if="loading">Loading authorizations…</p>
    <p v-else-if="items.length === 0">No authorizations found.</p>
    <table v-else>
      <thead><tr><th>Author ID</th><th>User ID</th><th>Permissions</th><th>Valid from</th><th>Valid to</th><th>Status</th><th v-if="isAdmin">Actions</th></tr></thead>
      <tbody><tr v-for="authorization in items" :key="authorization.id">
        <td>{{ authorization.author_id }}</td><td>{{ authorization.user_id }}</td><td>{{ authorization.permissions.join(', ') }}</td>
        <td>{{ authorization.valid_from }}</td><td>{{ authorization.valid_to }}</td><td>{{ authorization.validity_status }}</td>
        <td v-if="isAdmin"><button type="button" :data-test="`edit-authorization-${authorization.id}`" @click="openForm(authorization)">Edit</button><button v-if="!authorization.revoked_at" type="button" :data-test="`revoke-authorization-${authorization.id}`" @click="startRevoke(authorization.id)">Revoke</button></td>
      </tr></tbody>
    </table>
    <nav class="pagination" aria-label="Authorization pages">
      <button type="button" :disabled="query.page === 1 || loading" @click="changePage(query.page - 1)">Previous</button>
      <span>Page {{ query.page }} · {{ total }} total</span>
      <button type="button" data-test="next-authorizations" :disabled="query.page * query.page_size >= total || loading" @click="changePage(query.page + 1)">Next</button>
    </nav>
  </section>
</template>
