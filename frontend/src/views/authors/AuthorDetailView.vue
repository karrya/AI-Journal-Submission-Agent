<script setup lang="ts">
import axios from 'axios'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  createAuthorInstitution,
  createEmail,
  deleteAuthorInstitution,
  deleteEmail,
  getAuthor,
  listAllInstitutions,
  listAuthorInstitutions,
  listEmails,
  rolePermissions,
  updateAuthor,
  updateAuthorInstitution,
  updateEmail,
  type AuthorInstitutionLinkCreate,
  type AuthorInstitutionLinkResponse,
  type AuthorInstitutionLinkUpdate,
  type AuthorCreate,
  type AuthorResponse,
  type AuthorUpdate,
  type EmailCreate,
  type EmailResponse,
  type EmailUpdate,
  type InstitutionSummaryResponse,
  type PermissionCode,
} from '../../api/authors'
import EmailTable from '../../components/EmailTable.vue'
import InstitutionLinkForm from '../../components/InstitutionLinkForm.vue'
import AuthorForm from '../../components/AuthorForm.vue'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{
  authorId: string
  permissions?: PermissionCode[]
}>()

const auth = useAuthStore()
const author = ref<AuthorResponse | null>(null)
const emails = ref<EmailResponse[]>([])
const institutions = ref<AuthorInstitutionLinkResponse[]>([])
const loading = ref(false)
const errorMessage = ref('')
const emailMessage = ref('')
const institutionMessage = ref('')
const emailBusy = ref(false)
const emailTableKey = ref(0)
const showAffiliationForm = ref(false)
const affiliationBusy = ref(false)
const affiliationError = ref('')
const institutionOptions = ref<InstitutionSummaryResponse[]>([])
const institutionOptionsLoaded = ref(false)
const showAuthorForm = ref(false)
const authorBusy = ref(false)
const authorMutationError = ref('')
const editingLink = ref<AuthorInstitutionLinkResponse | null>(null)
const deletingLinkId = ref<string | null>(null)
const affiliationDeleteConfirmed = ref(false)
let loadSequence = 0

const effectivePermissions = computed(() => props.permissions ?? rolePermissions(auth.user?.roles ?? []))
const canReadEmails = computed(() => effectivePermissions.value.includes('author:email:read'))
const canReadInstitutions = computed(() => effectivePermissions.value.includes('author:profile:read'))
const canManage = computed(() => canReadInstitutions.value && effectivePermissions.value.includes('author:profile:update'))

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
}

function isForbidden(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 403
}

function isCurrent(sequence: number, authorId: string): boolean {
  return sequence === loadSequence && authorId === props.authorId
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  const authorId = props.authorId
  loading.value = true
  authorBusy.value = false
  emailBusy.value = false
  affiliationBusy.value = false
  author.value = null
  emails.value = []
  institutions.value = []
  showAuthorForm.value = false
  showAffiliationForm.value = false
  editingLink.value = null
  deletingLinkId.value = null
  errorMessage.value = ''
  emailMessage.value = canReadEmails.value ? '' : 'Email permission is not available.'
  institutionMessage.value = canReadInstitutions.value ? '' : 'Institution permission is not available.'
  try {
    const result = await getAuthor(authorId)
    if (!isCurrent(sequence, authorId)) return
    author.value = result
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      errorMessage.value = safeError(error, 'Unable to load this author.')
      loading.value = false
    }
    return
  }

  const requests: Promise<void>[] = []
  if (canReadEmails.value) {
    requests.push(listEmails(authorId).then((page) => {
      if (isCurrent(sequence, authorId)) emails.value = page.items
    }).catch((error: unknown) => {
      if (!isCurrent(sequence, authorId)) return
      emails.value = []
      emailMessage.value = isForbidden(error)
        ? 'Emails are not available for this author.'
        : safeError(error, 'Unable to load emails.')
    }))
  }
  if (canReadInstitutions.value) {
    requests.push(listAuthorInstitutions(authorId).then((page) => {
      if (isCurrent(sequence, authorId)) institutions.value = page.items
    }).catch((error: unknown) => {
      if (!isCurrent(sequence, authorId)) return
      institutions.value = []
      institutionMessage.value = isForbidden(error)
        ? 'Institutions are not available for this author.'
        : safeError(error, 'Unable to load institutions.')
    }))
  }
  await Promise.all(requests)
  if (sequence === loadSequence) loading.value = false
}

async function saveAuthor(payload: AuthorCreate | AuthorUpdate): Promise<void> {
  if (authorBusy.value || !canManage.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  authorBusy.value = true
  authorMutationError.value = ''
  try {
    const result = await updateAuthor(authorId, payload as AuthorUpdate)
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    author.value = result
    showAuthorForm.value = false
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      authorMutationError.value = safeError(error, 'Unable to update the author.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) authorBusy.value = false
  }
}

async function refreshEmails(sequence: number, authorId: string): Promise<void> {
  try {
    const page = await listEmails(authorId)
    if (!isCurrent(sequence, authorId) || !canReadEmails.value) return
    emails.value = page.items
    emailMessage.value = ''
  } catch (error) {
    if (!isCurrent(sequence, authorId)) return
    emails.value = []
    emailMessage.value = isForbidden(error)
      ? 'Emails are not available for this author.'
      : safeError(error, 'Unable to load emails.')
  }
}

async function createEmailBinding(payload: EmailCreate): Promise<void> {
  if (emailBusy.value || !canManage.value || !canReadEmails.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  emailBusy.value = true
  emailMessage.value = ''
  try {
    await createEmail(authorId, payload)
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    await refreshEmails(sequence, authorId)
    if (isCurrent(sequence, authorId)) emailTableKey.value += 1
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      emailMessage.value = safeError(error, 'Unable to create the email binding.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) emailBusy.value = false
  }
}

async function updateEmailBinding(change: { emailId: string; payload: EmailUpdate }): Promise<void> {
  if (emailBusy.value || !canManage.value || !canReadEmails.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  emailBusy.value = true
  emailMessage.value = ''
  try {
    await updateEmail(authorId, change.emailId, change.payload)
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    await refreshEmails(sequence, authorId)
    if (isCurrent(sequence, authorId)) emailTableKey.value += 1
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      emailMessage.value = safeError(error, 'Unable to update the email binding.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) emailBusy.value = false
  }
}

async function deleteEmailBinding(change: { emailId: string; confirm_email_binding: true }): Promise<void> {
  if (emailBusy.value || !canManage.value || !canReadEmails.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  emailBusy.value = true
  emailMessage.value = ''
  try {
    await deleteEmail(authorId, change.emailId)
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    await refreshEmails(sequence, authorId)
    if (isCurrent(sequence, authorId)) emailTableKey.value += 1
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      emailMessage.value = safeError(error, 'Unable to unbind the email.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) emailBusy.value = false
  }
}

function preserveCurrentInstitution(link?: AuthorInstitutionLinkResponse): void {
  if (!link || institutionOptions.value.some((option) => option.id === link.institution_id)) return
  institutionOptions.value = [...institutionOptions.value, {
    id: link.institution_id,
    name: link.institution_name,
    city: link.city,
    country_code: link.country_code,
  }]
}

async function openAffiliationForm(link?: AuthorInstitutionLinkResponse): Promise<void> {
  if (!canManage.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  showAffiliationForm.value = true
  editingLink.value = link ?? null
  deletingLinkId.value = null
  affiliationError.value = ''
  if (institutionOptionsLoaded.value) {
    preserveCurrentInstitution(link)
    return
  }
  try {
    const options = await listAllInstitutions()
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    institutionOptions.value = options
    institutionOptionsLoaded.value = true
    preserveCurrentInstitution(link)
  } catch (error) {
    if (!isCurrent(sequence, authorId)) return
    institutionOptions.value = []
    institutionOptionsLoaded.value = false
    preserveCurrentInstitution(link)
    affiliationError.value = safeError(error, 'Unable to load institution choices.')
  }
}

async function refreshInstitutions(sequence: number, authorId: string): Promise<void> {
  try {
    const page = await listAuthorInstitutions(authorId)
    if (!isCurrent(sequence, authorId) || !canReadInstitutions.value) return
    institutions.value = page.items
    institutionMessage.value = ''
  } catch (error) {
    if (!isCurrent(sequence, authorId)) return
    institutions.value = []
    institutionMessage.value = isForbidden(error)
      ? 'Institutions are not available for this author.'
      : safeError(error, 'Unable to load institutions.')
  }
}

async function saveAffiliation(
  payload: AuthorInstitutionLinkCreate | AuthorInstitutionLinkUpdate,
): Promise<void> {
  if (affiliationBusy.value || !canManage.value) return
  const sequence = loadSequence
  const authorId = props.authorId
  const linkId = editingLink.value?.id ?? null
  affiliationBusy.value = true
  affiliationError.value = ''
  try {
    if (linkId) {
      await updateAuthorInstitution(
        authorId,
        linkId,
        payload as AuthorInstitutionLinkUpdate,
      )
    } else {
      await createAuthorInstitution(authorId, payload as AuthorInstitutionLinkCreate)
    }
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    await refreshInstitutions(sequence, authorId)
    if (!isCurrent(sequence, authorId)) return
    showAffiliationForm.value = false
    editingLink.value = null
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      affiliationError.value = safeError(error, 'Unable to save the affiliation.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) affiliationBusy.value = false
  }
}

function startAffiliationDelete(linkId: string): void {
  if (!canManage.value) return
  deletingLinkId.value = linkId
  affiliationDeleteConfirmed.value = false
  showAffiliationForm.value = false
  affiliationError.value = ''
}

async function confirmAffiliationDelete(): Promise<void> {
  if (!deletingLinkId.value || affiliationBusy.value || !canManage.value) return
  if (!affiliationDeleteConfirmed.value) {
    affiliationError.value = 'Confirm the affiliation removal separately before deleting.'
    return
  }
  const sequence = loadSequence
  const authorId = props.authorId
  const linkId = deletingLinkId.value
  affiliationBusy.value = true
  affiliationError.value = ''
  try {
    await deleteAuthorInstitution(authorId, linkId)
    if (!isCurrent(sequence, authorId) || !canManage.value) return
    await refreshInstitutions(sequence, authorId)
    if (isCurrent(sequence, authorId)) deletingLinkId.value = null
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      affiliationError.value = safeError(error, 'Unable to remove the affiliation.')
    }
  } finally {
    if (isCurrent(sequence, authorId)) affiliationBusy.value = false
  }
}

watch([() => props.authorId, effectivePermissions], () => void load(), { immediate: true, deep: true })
</script>

<template>
  <section class="management-page" aria-labelledby="author-detail-title">
    <RouterLink to="/authors">Back to authors</RouterLink>
    <h1 id="author-detail-title">Author detail</h1>
    <p v-if="loading">Loading author…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <template v-if="author">
      <dl class="detail-grid">
        <div><dt>Display name</dt><dd>{{ author.display_name }}</dd></div>
        <div v-if="author.given_name != null"><dt>Given name</dt><dd>{{ author.given_name }}</dd></div>
        <div v-if="author.middle_name != null"><dt>Middle name</dt><dd>{{ author.middle_name }}</dd></div>
        <div v-if="author.family_name != null"><dt>Family name</dt><dd>{{ author.family_name }}</dd></div>
        <div v-if="author.orcid != null"><dt>ORCID</dt><dd>{{ author.orcid }}</dd></div>
        <div><dt>Status</dt><dd>{{ author.status }}</dd></div>
        <div v-if="author.phone_country_code != null"><dt>Phone country code</dt><dd>{{ author.phone_country_code }}</dd></div>
        <div v-if="author.phone_number != null"><dt>Phone number</dt><dd>{{ author.phone_number }}</dd></div>
        <div v-if="author.notes != null"><dt>Notes</dt><dd>{{ author.notes }}</dd></div>
      </dl>
      <button v-if="canManage && !showAuthorForm" type="button" data-test="edit-author" @click="showAuthorForm = true">Edit author</button>
      <p v-if="authorMutationError" class="form-error" role="alert">{{ authorMutationError }}</p>
      <AuthorForm
        v-if="canManage && showAuthorForm"
        data-test="author-edit-form"
        :author="author"
        :submitting="authorBusy"
        @submit="saveAuthor"
        @cancel="showAuthorForm = false"
      />
    </template>

    <section aria-labelledby="email-title">
      <h2 id="email-title">Emails</h2>
      <p v-if="emailMessage" role="status">{{ emailMessage }}</p>
      <EmailTable
        v-if="canReadEmails"
        :key="`${authorId}-${emailTableKey}`"
        :emails="emails"
        :can-manage="canManage"
        :busy="emailBusy"
        :suppress-empty-state="Boolean(emailMessage)"
        @create="createEmailBinding"
        @update="updateEmailBinding"
        @delete="deleteEmailBinding"
      />
      <p v-else-if="!emailMessage">Email permission is not available.</p>
    </section>

    <section aria-labelledby="institution-title">
      <h2 id="institution-title">Institutions</h2>
      <p v-if="institutionMessage" role="status">{{ institutionMessage }}</p>
      <p v-else-if="!loading && institutions.length === 0">No institution links.</p>
      <table v-else>
        <thead><tr><th>Institution</th><th>Department</th><th>Position</th><th>Current</th><th v-if="canManage">Actions</th></tr></thead>
        <tbody><tr v-for="link in institutions" :key="link.id">
          <td>{{ link.institution_name }}</td><td>{{ link.department ?? '—' }}</td><td>{{ link.position_title ?? '—' }}</td><td>{{ link.is_current ? 'Yes' : 'No' }}</td>
          <td v-if="canManage">
            <button type="button" :data-test="`edit-affiliation-${link.id}`" @click="openAffiliationForm(link)">Edit</button>
            <button type="button" :data-test="`delete-affiliation-${link.id}`" @click="startAffiliationDelete(link.id)">Remove</button>
          </td>
        </tr></tbody>
      </table>
      <button v-if="canManage && !showAffiliationForm" type="button" data-test="add-affiliation" @click="openAffiliationForm()">Add affiliation</button>
      <p v-if="affiliationError" class="form-error" role="alert">{{ affiliationError }}</p>
      <section v-if="canManage && deletingLinkId" class="confirmation-panel" aria-label="Confirm affiliation removal">
        <p>Remove this affiliation from the author? This action requires separate confirmation.</p>
        <label class="confirmation-control"><input v-model="affiliationDeleteConfirmed" data-test="affiliation-delete-confirm" type="checkbox"> I confirm this affiliation removal.</label>
        <button type="button" :data-test="`confirm-delete-affiliation-${deletingLinkId}`" :disabled="affiliationBusy" @click="confirmAffiliationDelete">Confirm removal</button>
        <button type="button" @click="deletingLinkId = null">Cancel</button>
      </section>
      <InstitutionLinkForm
        v-if="canManage && showAffiliationForm"
        data-test="affiliation-form"
        :institutions="institutionOptions"
        :link="editingLink"
        :submitting="affiliationBusy"
        @submit="saveAffiliation"
        @cancel="showAffiliationForm = false"
      />
    </section>
  </section>
</template>
