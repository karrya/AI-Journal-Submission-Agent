<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  createAuthorization,
  getAuthorizationOptions,
  listAuthorizations,
  revokeAuthorization,
  updateAuthorization,
  PERMISSION_CODES,
  type AuthorizationListQuery,
  type AuthorizationOptions,
  type AuthorizationResponse,
  type PermissionCode,
  type SortOrder,
} from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import {
  AUTHORIZATION_STATUS_LABELS,
  displayText,
  PERMISSION_LABELS,
} from '../../utils/display'

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
const authorOptions = ref<AuthorizationOptions['authors']>([])
const userOptions = ref<AuthorizationOptions['users']>([])
const optionsLoading = ref(false)
const optionsLoaded = ref(false)
const authorOptionMissing = computed(() => Boolean(
  editingId.value
  && optionsLoaded.value
  && form.author_id
  && !authorOptions.value.some((author) => author.id === form.author_id),
))
const userOptionMissing = computed(() => Boolean(
  editingId.value
  && optionsLoaded.value
  && form.user_id
  && !userOptions.value.some((user) => user.id === form.user_id),
))
let optionsSequence = 0
const revokeReason = ref('')
const revokeConfirmed = ref(false)
let loadSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
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
    errorMessage.value = safeError(error, '无法加载授权。')
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

async function loadOptions(): Promise<void> {
  if (!isAdmin.value || optionsLoaded.value || optionsLoading.value) return
  const sequence = ++optionsSequence
  optionsLoading.value = true
  try {
    const options = await getAuthorizationOptions()
    if (sequence !== optionsSequence) return
    authorOptions.value = options.authors
    userOptions.value = options.users
    optionsLoaded.value = true
  } catch (error) {
    if (sequence === optionsSequence) {
      errorMessage.value = safeError(error, '无法加载授权选项。')
    }
  } finally {
    if (sequence === optionsSequence) optionsLoading.value = false
  }
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
  void loadOptions()
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
    errorMessage.value = '请选择作者和用户。'
    return
  }
  if (form.permissions.length === 0) {
    errorMessage.value = '请至少选择一项权限。'
    return
  }
  if (!form.valid_from || !form.valid_to) {
    errorMessage.value = '请填写开始时间和结束时间。'
    return
  }
  const validFrom = isoDate(form.valid_from)
  const validTo = isoDate(form.valid_to)
  if (!validFrom || !validTo) {
    errorMessage.value = '开始时间和结束时间必须是有效日期。'
    return
  }
  const startMs = new Date(validFrom).getTime()
  const endMs = new Date(validTo).getTime()
  if (endMs <= startMs) {
    errorMessage.value = '结束时间必须晚于开始时间。'
    return
  }
  if (endMs <= Date.now()) {
    errorMessage.value = '结束时间必须晚于当前时间。'
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
    errorMessage.value = safeError(error, '无法保存授权。')
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
    errorMessage.value = '继续前请单独确认撤销授权。'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    await revokeAuthorization(revokingId.value, { reason: nullable(revokeReason.value) })
    revokingId.value = null
    await load()
  } catch (error) {
    errorMessage.value = safeError(error, '无法撤销授权。')
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
    <h1 id="authorization-title">作者授权</h1>
    <p>授权仅限九项既定权限，且必须设置明确的开始和结束时间。</p>
    <div class="toolbar">
      <label>用户 ID<input v-model="query.user_id" @change="query.page = 1; load()"></label>
      <label>排序<select v-model="query.sort" @change="sortChanged"><option value="created_at">创建时间</option><option value="updated_at">更新时间</option><option value="valid_from">开始时间</option><option value="valid_to">结束时间</option></select></label>
      <label>顺序<select v-model="query.order" @change="sortChanged"><option value="desc">降序</option><option value="asc">升序</option></select></label>
      <button v-if="isAdmin" class="action-button action-button--permission" type="button" data-test="add-authorization" @click="openForm()">添加授权</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <form v-if="showForm" data-test="authorization-form" class="stacked-form" novalidate @submit.prevent="save">
      <h2>{{ editingId ? '编辑授权' : '添加授权' }}</h2>
      <div class="form-grid">
        <label>作者
          <select v-model="form.author_id" data-test="authorization-author-id" :disabled="Boolean(editingId) || optionsLoading" required>
            <option value="" disabled>请选择作者</option>
            <option v-for="author in authorOptions" :key="author.id" :value="author.id">{{ author.display_name }}</option>
            <option v-if="authorOptionMissing" :value="form.author_id">当前作者（已失效）</option>
          </select>
        </label>
        <label>用户
          <select v-model="form.user_id" data-test="authorization-user-id" :disabled="Boolean(editingId) || optionsLoading" required>
            <option value="" disabled>请选择用户</option>
            <option v-for="user in userOptions" :key="user.id" :value="user.id">{{ user.display_name }}（@{{ user.username }}）</option>
            <option v-if="userOptionMissing" :value="form.user_id">当前用户（已失效）</option>
          </select>
        </label>
        <label>开始时间<input v-model="form.valid_from" data-test="valid-from" type="datetime-local" required></label>
        <label>结束时间<input v-model="form.valid_to" data-test="valid-to" type="datetime-local" required></label>
      </div>
      <fieldset>
        <legend>权限</legend>
        <label v-for="code in PERMISSION_CODES" :key="code" class="permission-option"><input v-model="form.permissions" data-test="permission-option" type="checkbox" :value="code"> {{ displayText(PERMISSION_LABELS, code) }}</label>
      </fieldset>
      <label>授权依据<input v-model="form.evidence_ref" maxlength="1024"></label>
      <label>备注<textarea v-model="form.notes" rows="3"></textarea></label>
      <button class="action-button action-button--permission" type="submit" :disabled="saving || optionsLoading || !optionsLoaded">保存授权</button>
      <button class="action-button action-button--neutral" type="button" @click="showForm = false">取消</button>
    </form>

    <section v-if="revokingId" class="confirmation-panel" aria-label="确认撤销授权">
      <h2>撤销授权</h2>
      <p>撤销与编辑相互独立，并将在授权对象的下次请求时生效。</p>
      <label>原因<textarea v-model="revokeReason" data-test="revoke-reason" rows="3" maxlength="2000"></textarea></label>
      <label class="confirmation-control"><input v-model="revokeConfirmed" data-test="revoke-confirm" type="checkbox"> 我确认撤销此授权。</label>
      <button class="action-button action-button--danger" type="button" :data-test="`confirm-revoke-${revokingId}`" :disabled="saving" @click="confirmRevoke">确认撤销</button>
      <button class="action-button action-button--neutral" type="button" @click="revokingId = null">取消</button>
    </section>

    <p v-if="loading">正在加载授权…</p>
    <p v-else-if="!errorMessage && items.length === 0">未找到授权。</p>
    <table v-else>
      <thead><tr><th>作者 ID</th><th>用户 ID</th><th>权限</th><th>开始时间</th><th>结束时间</th><th>状态</th><th v-if="isAdmin">操作</th></tr></thead>
      <tbody><tr v-for="authorization in items" :key="authorization.id">
        <td>{{ authorization.author_id }}</td><td>{{ authorization.user_id }}</td><td>{{ authorization.permissions.map((code) => displayText(PERMISSION_LABELS, code)).join('、') }}</td>
        <td>{{ authorization.valid_from }}</td><td>{{ authorization.valid_to }}</td><td>{{ displayText(AUTHORIZATION_STATUS_LABELS, authorization.validity_status) }}</td>
        <td v-if="isAdmin"><button class="action-button action-button--compact action-button--edit" type="button" :data-test="`edit-authorization-${authorization.id}`" @click="openForm(authorization)">编辑</button><button v-if="!authorization.revoked_at" class="action-button action-button--compact action-button--danger" type="button" :data-test="`revoke-authorization-${authorization.id}`" @click="startRevoke(authorization.id)">撤销</button></td>
      </tr></tbody>
    </table>
    <nav class="pagination" aria-label="授权分页">
      <button class="action-button action-button--compact action-button--neutral" type="button" :disabled="query.page === 1 || loading" @click="changePage(query.page - 1)">上一页</button>
      <span>第 {{ query.page }} 页 · 共 {{ total }} 条</span>
      <button class="action-button action-button--compact action-button--neutral" type="button" data-test="next-authorizations" :disabled="query.page * query.page_size >= total || loading" @click="changePage(query.page + 1)">下一页</button>
    </nav>
  </section>
</template>
