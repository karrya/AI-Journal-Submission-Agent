<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import {
  createUser,
  getUser,
  listUsers,
  resetUserPassword,
  updateUser,
  type ManagedUser,
  type RoleCode,
  type UserListQuery,
  type UserStatus,
} from '../../api/users'
import { useAuthStore } from '../../stores/auth'
import { displayText, ROLE_LABELS } from '../../utils/display'
import { showSaveSuccess } from '../../utils/feedback'
import AppModal from '../../components/AppModal.vue'
import { useDirtyGuard } from '../../composables/useDirtyGuard'

const auth = useAuthStore()
const router = useRouter()
const saving = ref(false)
const roleCodes = Object.keys(ROLE_LABELS) as RoleCode[]
let loadSequence = 0
let editSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

const users = ref<ManagedUser[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const creating = ref(false)
const showCreate = ref(false)
const createModal = ref<InstanceType<typeof AppModal> | null>(null)
const query = reactive({
  page: 1,
  page_size: 20,
  name: '',
  status: '' as UserStatus | '',
  sort: 'created_at' as NonNullable<UserListQuery['sort']>,
  order: 'desc' as SortOrder,
})
const createForm = reactive({
  username: '',
  display_name: '',
  password: '',
  password_confirmation: '',
  roles: [] as RoleCode[],
})
const createGuard = useDirtyGuard(() => createForm)

function openCreate(): void {
  createGuard.capture()
  errorMessage.value = ''
  showCreate.value = true
}

function resetCreateForm(): void {
  Object.assign(createForm, {
    username: '',
    display_name: '',
    password: '',
    password_confirmation: '',
    roles: [],
  })
  createGuard.capture()
  showCreate.value = false
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await listUsers({ ...query, status: query.status || undefined })
    if (sequence !== loadSequence) return
    users.value = result.items
    total.value = result.total
  } catch (error) {
    if (sequence === loadSequence) {
      users.value = []
      total.value = 0
      errorMessage.value = safeError(error, '无法加载用户。')
    }
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function saveCreate(): Promise<void> {
  if (creating.value) return
  errorMessage.value = ''
  if (!createForm.username.trim() || !createForm.display_name.trim()
    || !createForm.password || !createForm.password_confirmation) {
    errorMessage.value = '请填写用户名、显示姓名和两次密码。'
    return
  }
  if (createForm.password !== createForm.password_confirmation) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  if (createForm.roles.length === 0) {
    errorMessage.value = '请至少选择一个角色。'
    return
  }
  creating.value = true
  try {
    await createUser({
      username: createForm.username.trim(),
      display_name: createForm.display_name.trim(),
      password: createForm.password,
      password_confirmation: createForm.password_confirmation,
      roles: [...createForm.roles],
    })
    showCreate.value = false
    Object.assign(createForm, {
      username: '',
      display_name: '',
      password: '',
      password_confirmation: '',
      roles: [],
    })
    createGuard.capture()
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法创建用户。')
  } finally {
    creating.value = false
  }
}

const editing = ref<ManagedUser | null>(null)
const editModal = ref<InstanceType<typeof AppModal> | null>(null)
const resetting = ref<ManagedUser | null>(null)
const resetModal = ref<InstanceType<typeof AppModal> | null>(null)
const editForm = reactive({
  display_name: '',
  roles: [] as RoleCode[],
  status: 'active' as UserStatus,
})
const resetForm = reactive({ new_password: '', password_confirmation: '' })
const editGuard = useDirtyGuard(() => editForm)
const resetGuard = useDirtyGuard(() => resetForm)

async function openEdit(user: ManagedUser): Promise<void> {
  const sequence = ++editSequence
  errorMessage.value = ''
  try {
    const detail = await getUser(user.id)
    if (sequence !== editSequence) return
    editing.value = detail
    resetting.value = null
    Object.assign(editForm, {
      display_name: detail.display_name,
      roles: [...detail.roles],
      status: detail.status,
    })
    editGuard.capture()
  } catch (error) {
    if (sequence === editSequence) {
      errorMessage.value = safeError(error, '无法加载用户详情。')
    }
  }
}

async function saveEdit(): Promise<void> {
  const current = editing.value
  if (!current || saving.value) return
  errorMessage.value = ''
  if (!editForm.display_name.trim()) {
    errorMessage.value = '请填写显示姓名。'
    return
  }
  if (editForm.roles.length === 0) {
    errorMessage.value = '请至少选择一个角色。'
    return
  }
  saving.value = true
  try {
    await updateUser(current.id, {
      display_name: editForm.display_name.trim(),
      roles: [...editForm.roles],
      status: editForm.status,
    })
    editing.value = null
    editSequence += 1
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法更新用户。')
  } finally {
    saving.value = false
  }
}

function openReset(user: ManagedUser): void {
  editSequence += 1
  errorMessage.value = ''
  editing.value = null
  resetting.value = user
  Object.assign(resetForm, { new_password: '', password_confirmation: '' })
  resetGuard.capture()
}

async function saveReset(): Promise<void> {
  const current = resetting.value
  if (!current || saving.value) return
  errorMessage.value = ''
  if (!resetForm.new_password || !resetForm.password_confirmation) {
    errorMessage.value = '请填写两次新密码。'
    return
  }
  if (resetForm.new_password !== resetForm.password_confirmation) {
    errorMessage.value = '两次输入的密码不一致。'
    return
  }
  saving.value = true
  try {
    await resetUserPassword(current.id, {
      new_password: resetForm.new_password,
      password_confirmation: resetForm.password_confirmation,
    })
    resetting.value = null
    if (current.id === auth.user?.id) {
      auth.clearSession()
      await router.replace({ name: 'login' })
      return
    }
    await load()
    showSaveSuccess()
  } catch (error) {
    errorMessage.value = safeError(error, '无法重置密码。')
  } finally {
    saving.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="user-list-title">
    <h1 id="user-list-title">用户管理</h1>
    <div class="toolbar">
      <label>姓名或用户名<input v-model="query.name" data-test="user-name-filter"></label>
      <label>状态
        <select v-model="query.status" data-test="user-status-filter">
          <option value="">全部状态</option>
          <option value="active">启用</option>
          <option value="disabled">停用</option>
        </select>
      </label>
      <label>排序
        <select v-model="query.sort" data-test="user-sort" @change="query.page = 1; load()">
          <option value="created_at">创建时间</option>
          <option value="updated_at">更新时间</option>
          <option value="username">用户名</option>
          <option value="display_name">显示姓名</option>
          <option value="last_login_at">最后登录时间</option>
        </select>
      </label>
      <label>顺序
        <select v-model="query.order" @change="query.page = 1; load()">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </label>
      <button class="action-button action-button--neutral" type="button" data-test="apply-user-filters" @click="query.page = 1; load()">应用筛选</button>
      <button class="action-button action-button--create" type="button" data-test="add-user" @click="openCreate">新增用户</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <AppModal ref="createModal" v-model="showCreate" title="新增用户" description="创建本地工作区用户并分配初始角色。" width="720px" :busy="creating" :dirty="() => createGuard.dirty.value" :error="errorMessage" @cancel="resetCreateForm">
      <form data-test="user-create-form" class="stacked-form" novalidate @submit.prevent="saveCreate">
        <div class="form-grid">
          <label>用户名<input v-model="createForm.username" data-test="new-username" maxlength="64" required></label>
          <label>显示姓名<input v-model="createForm.display_name" data-test="new-display-name" maxlength="128" required></label>
          <label>初始密码<input v-model="createForm.password" data-test="new-password" type="password" autocomplete="new-password" required></label>
          <label>确认初始密码<input v-model="createForm.password_confirmation" data-test="new-password-confirmation" type="password" autocomplete="new-password" required></label>
        </div>
        <fieldset>
          <legend>角色</legend>
          <label v-for="code in roleCodes" :key="code">
            <input v-model="createForm.roles" type="checkbox" :value="code" :data-test="`create-role-${code}`">
            {{ displayText(ROLE_LABELS, code) }}
          </label>
        </fieldset>
        <div class="form-actions">
          <button class="action-button action-button--create" type="submit" :disabled="creating">保存用户</button>
          <button class="action-button action-button--neutral" type="button" @click="createModal?.requestClose()">取消</button>
        </div>
      </form>
    </AppModal>

    <AppModal ref="editModal" :model-value="Boolean(editing)" title="编辑用户" description="调整用户显示姓名、角色和启用状态。" width="680px" :busy="saving" :dirty="() => editGuard.dirty.value" :error="errorMessage" @update:model-value="editing = $event ? editing : null">
      <form v-if="editing" data-test="user-edit-form" class="stacked-form" novalidate @submit.prevent="saveEdit">
        <label>显示姓名<input v-model="editForm.display_name" data-test="edit-display-name" maxlength="128" required></label>
        <fieldset>
          <legend>角色</legend>
          <label v-for="code in roleCodes" :key="code">
            <input v-model="editForm.roles" type="checkbox" :value="code" :data-test="`edit-role-${code}`">
            {{ displayText(ROLE_LABELS, code) }}
          </label>
        </fieldset>
        <label>状态
          <select v-model="editForm.status" data-test="edit-status">
            <option value="active">启用</option>
            <option value="disabled">停用</option>
          </select>
        </label>
        <p v-if="editing.id === auth.user?.id">不能停用本人或移除本人的系统管理员角色。</p>
        <div class="form-actions">
          <button class="action-button action-button--create" type="submit" :disabled="saving">保存修改</button>
          <button class="action-button action-button--neutral" type="button" @click="editModal?.requestClose()">取消</button>
        </div>
      </form>
    </AppModal>

    <AppModal ref="resetModal" :model-value="Boolean(resetting)" title="重置密码" description="设置用户的新密码，保存后立即生效。" width="560px" :busy="saving" :dirty="() => resetGuard.dirty.value" :error="errorMessage" @update:model-value="resetting = $event ? resetting : null">
      <form v-if="resetting" data-test="user-reset-form" class="stacked-form" novalidate @submit.prevent="saveReset">
        <label>新密码<input v-model="resetForm.new_password" data-test="reset-new-password" type="password" autocomplete="new-password" required></label>
        <label>确认新密码<input v-model="resetForm.password_confirmation" data-test="reset-password-confirmation" type="password" autocomplete="new-password" required></label>
        <div class="form-actions">
          <button class="action-button action-button--create" type="submit" :disabled="saving">保存新密码</button>
          <button class="action-button action-button--neutral" type="button" @click="resetModal?.requestClose()">取消</button>
        </div>
      </form>
    </AppModal>

    <p v-if="loading">正在加载用户…</p>
    <p v-else-if="!errorMessage && users.length === 0">未找到用户。</p>
    <table v-else data-test="user-list">
      <thead><tr><th>用户名</th><th>显示姓名</th><th>角色</th><th>状态</th><th>需改密</th><th>最后登录</th><th>操作</th></tr></thead>
      <tbody><tr v-for="user in users" :key="user.id">
        <td>{{ user.username }}</td>
        <td>{{ user.display_name }}</td>
        <td>{{ user.roles.map((role) => displayText(ROLE_LABELS, role)).join('、') }}</td>
        <td>{{ user.status === 'active' ? '启用' : '停用' }}</td>
        <td>{{ user.must_change_password ? '是' : '否' }}</td>
        <td>{{ user.last_login_at ?? '—' }}</td>
        <td>
          <button class="action-button action-button--compact action-button--neutral" type="button" :data-test="`edit-user-${user.id}`" @click="openEdit(user)">编辑</button>
          <button class="action-button action-button--compact action-button--neutral" type="button" :data-test="`reset-user-${user.id}`" @click="openReset(user)">重置密码</button>
        </td>
      </tr></tbody>
    </table>
    <nav class="pagination" aria-label="用户分页">
      <span>第 {{ query.page }} 页 · 共 {{ total }} 条</span>
      <button class="action-button action-button--compact action-button--neutral" type="button" data-test="next-users" :disabled="query.page * query.page_size >= total || loading" @click="query.page += 1; load()">下一页</button>
    </nav>
  </section>
</template>
