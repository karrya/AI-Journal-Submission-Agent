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
import { AUTHOR_STATUS_LABELS, displayText } from '../../utils/display'
import { showSaveSuccess } from '../../utils/feedback'

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
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
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
  emailMessage.value = canReadEmails.value ? '' : '当前没有查看邮箱的权限。'
  institutionMessage.value = canReadInstitutions.value ? '' : '当前没有查看单位的权限。'
  try {
    const result = await getAuthor(authorId)
    if (!isCurrent(sequence, authorId)) return
    author.value = result
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      errorMessage.value = safeError(error, '无法加载该作者。')
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
        ? '无法查看该作者的邮箱。'
        : safeError(error, '无法加载邮箱。')
    }))
  }
  if (canReadInstitutions.value) {
    requests.push(listAuthorInstitutions(authorId).then((page) => {
      if (isCurrent(sequence, authorId)) institutions.value = page.items
    }).catch((error: unknown) => {
      if (!isCurrent(sequence, authorId)) return
      institutions.value = []
      institutionMessage.value = isForbidden(error)
        ? '无法查看该作者的单位。'
        : safeError(error, '无法加载单位。')
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
    showSaveSuccess()
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      authorMutationError.value = safeError(error, '无法更新作者。')
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
      ? '无法查看该作者的邮箱。'
      : safeError(error, '无法加载邮箱。')
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
    if (isCurrent(sequence, authorId)) {
      emailTableKey.value += 1
      showSaveSuccess()
    }
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      emailMessage.value = safeError(error, '无法创建邮箱绑定。')
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
    if (isCurrent(sequence, authorId)) {
      emailTableKey.value += 1
      showSaveSuccess()
    }
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      emailMessage.value = safeError(error, '无法更新邮箱绑定。')
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
      emailMessage.value = safeError(error, '无法解绑邮箱。')
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
    affiliationError.value = safeError(error, '无法加载单位选项。')
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
      ? '无法查看该作者的单位。'
      : safeError(error, '无法加载单位。')
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
    showSaveSuccess()
  } catch (error) {
    if (isCurrent(sequence, authorId)) {
      affiliationError.value = safeError(error, '无法保存单位关联。')
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
    affiliationError.value = '删除前请单独确认移除单位关联。'
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
      affiliationError.value = safeError(error, '无法移除单位关联。')
    }
  } finally {
    if (isCurrent(sequence, authorId)) affiliationBusy.value = false
  }
}

watch([() => props.authorId, effectivePermissions], () => void load(), { immediate: true, deep: true })
</script>

<template>
  <section class="management-page" aria-labelledby="author-detail-title">
    <RouterLink class="action-button action-button--neutral" to="/authors">返回作者列表</RouterLink>
    <h1 id="author-detail-title">作者详情</h1>
    <p v-if="loading">正在加载作者…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <template v-if="author">
      <dl class="detail-grid">
        <div><dt>显示姓名</dt><dd>{{ author.display_name }}</dd></div>
        <div v-if="author.given_name != null"><dt>名</dt><dd>{{ author.given_name }}</dd></div>
        <div v-if="author.middle_name != null"><dt>中间名</dt><dd>{{ author.middle_name }}</dd></div>
        <div v-if="author.family_name != null"><dt>姓</dt><dd>{{ author.family_name }}</dd></div>
        <div v-if="author.orcid != null"><dt>ORCID</dt><dd>{{ author.orcid }}</dd></div>
        <div><dt>状态</dt><dd>{{ displayText(AUTHOR_STATUS_LABELS, author.status) }}</dd></div>
        <div v-if="author.phone_country_code != null"><dt>电话国家代码</dt><dd>{{ author.phone_country_code }}</dd></div>
        <div v-if="author.phone_number != null"><dt>电话号码</dt><dd>{{ author.phone_number }}</dd></div>
        <div v-if="author.notes != null"><dt>备注</dt><dd>{{ author.notes }}</dd></div>
      </dl>
      <button v-if="canManage && !showAuthorForm" class="action-button action-button--edit" type="button" data-test="edit-author" @click="showAuthorForm = true">编辑作者</button>
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
      <h2 id="email-title">邮箱</h2>
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
      <p v-else-if="!emailMessage">当前没有查看邮箱的权限。</p>
    </section>

    <section aria-labelledby="institution-title">
      <h2 id="institution-title">单位</h2>
      <p v-if="institutionMessage" role="status">{{ institutionMessage }}</p>
      <p v-else-if="!loading && institutions.length === 0">暂无单位关联。</p>
      <table v-else>
        <thead><tr><th>单位</th><th>院系</th><th>职务</th><th>当前单位</th><th v-if="canManage">操作</th></tr></thead>
        <tbody><tr v-for="link in institutions" :key="link.id">
          <td>{{ link.institution_name }}</td><td>{{ link.department ?? '—' }}</td><td>{{ link.position_title ?? '—' }}</td><td>{{ link.is_current ? '是' : '否' }}</td>
          <td v-if="canManage">
            <button class="action-button action-button--compact action-button--edit" type="button" :data-test="`edit-affiliation-${link.id}`" @click="openAffiliationForm(link)">编辑</button>
            <button class="action-button action-button--compact action-button--danger" type="button" :data-test="`delete-affiliation-${link.id}`" @click="startAffiliationDelete(link.id)">移除</button>
          </td>
        </tr></tbody>
      </table>
      <button v-if="canManage && !showAffiliationForm" class="action-button action-button--create" type="button" data-test="add-affiliation" @click="openAffiliationForm()">添加单位关联</button>
      <p v-if="affiliationError" class="form-error" role="alert">{{ affiliationError }}</p>
      <section v-if="canManage && deletingLinkId" class="confirmation-panel" aria-label="确认移除单位关联">
        <p>确定从该作者移除单位关联吗？此操作需单独确认。</p>
        <label class="confirmation-control"><input v-model="affiliationDeleteConfirmed" data-test="affiliation-delete-confirm" type="checkbox"> 我确认移除该单位关联。</label>
        <button class="action-button action-button--danger" type="button" :data-test="`confirm-delete-affiliation-${deletingLinkId}`" :disabled="affiliationBusy" @click="confirmAffiliationDelete">确认移除</button>
        <button class="action-button action-button--neutral" type="button" @click="deletingLinkId = null">取消</button>
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
