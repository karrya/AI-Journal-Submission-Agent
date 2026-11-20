<script setup lang="ts">
import { reactive, ref, watch, computed } from 'vue'
import type { EmailCreate, EmailResponse, EmailUpdate } from '../api/authors'
import AppModal from './AppModal.vue'
import AppConfirmDialog from './AppConfirmDialog.vue'
import { useDirtyGuard } from '../composables/useDirtyGuard'
import {
  displayText,
  EMAIL_AUTHORIZATION_LABELS,
  EMAIL_PURPOSE_LABELS,
  EMAIL_VERIFICATION_LABELS,
} from '../utils/display'

const props = withDefaults(defineProps<{
  emails: EmailResponse[]
  canManage?: boolean
  busy?: boolean
  suppressEmptyState?: boolean
  requestError?: string
}>(), {
  canManage: false,
  busy: false,
  suppressEmptyState: false,
  requestError: '',
})

const emit = defineEmits<{
  create: [payload: EmailCreate]
  update: [change: { emailId: string; payload: EmailUpdate }]
  delete: [change: { emailId: string; confirm_email_binding: true }]
}>()

const createForm = reactive({
  email: '',
  purpose: 'communication' as 'communication' | 'registration' | 'backup' | 'institutional',
  is_primary: false,
  confirm: false,
})
const editForm = reactive({
  email: '',
  purpose: 'communication' as 'communication' | 'registration' | 'backup' | 'institutional',
  is_primary: false,
  confirm: false,
})
const editingId = ref<string | null>(null)
const editModal = ref<InstanceType<typeof AppModal> | null>(null)
const deletingId = ref<string | null>(null)
const deleteConfirmed = ref(false)
const showCreate = ref(false)
const createModal = ref<InstanceType<typeof AppModal> | null>(null)
const errorMessage = ref('')
const createGuard = useDirtyGuard(() => createForm)
const editGuard = useDirtyGuard(() => editForm)
const editingOpen = computed({
  get: () => editingId.value !== null,
  set: (open: boolean) => { if (!open) editingId.value = null },
})
const deletingOpen = computed({
  get: () => deletingId.value !== null,
  set: (open: boolean) => { if (!open) deletingId.value = null },
})
const dialogError = computed(() => errorMessage.value || props.requestError)

watch(() => props.canManage, (allowed) => {
  if (allowed) return
  editingId.value = null
  deletingId.value = null
  showCreate.value = false
  deleteConfirmed.value = false
  createForm.confirm = false
  editForm.confirm = false
  errorMessage.value = ''
})

function openCreate(): void {
  if (!props.canManage) return
  showCreate.value = true
  errorMessage.value = ''
}

function cancelCreate(): void {
  showCreate.value = false
  Object.assign(createForm, {
    email: '',
    purpose: 'communication',
    is_primary: false,
    confirm: false,
  })
  createGuard.capture()
}

function create(): void {
  if (!props.canManage) return
  errorMessage.value = ''
  if (!createForm.email.trim()) {
    errorMessage.value = '请填写邮箱地址。'
    return
  }
  if (!createForm.confirm) {
    errorMessage.value = '保存前请确认邮箱绑定。'
    return
  }
  emit('create', {
    email: createForm.email.trim(),
    purpose: createForm.purpose,
    is_primary: createForm.is_primary,
    confirm_email_binding: true,
  })
}

function startEdit(email: EmailResponse): void {
  if (!props.canManage) return
  editingId.value = email.id
  deletingId.value = null
  Object.assign(editForm, {
    email: email.email,
    purpose: email.purpose,
    is_primary: email.is_primary,
    confirm: false,
  })
  editGuard.capture()
  errorMessage.value = ''
}

function update(): void {
  if (!props.canManage || !editingId.value) return
  errorMessage.value = ''
  if (!editForm.email.trim()) {
    errorMessage.value = '请填写邮箱地址。'
    return
  }
  if (!editForm.confirm) {
    errorMessage.value = '保存变更前请确认邮箱绑定。'
    return
  }
  emit('update', {
    emailId: editingId.value,
    payload: {
      email: editForm.email.trim(),
      purpose: editForm.purpose,
      is_primary: editForm.is_primary,
      confirm_email_binding: true,
    },
  })
}

function startDelete(emailId: string): void {
  if (!props.canManage) return
  deletingId.value = emailId
  editingId.value = null
  deleteConfirmed.value = false
  errorMessage.value = ''
}

function confirmRemove(): void {
  if (deletingId.value) remove(deletingId.value)
}

function remove(emailId: string): void {
  if (!props.canManage) return
  if (!deleteConfirmed.value) {
    errorMessage.value = '删除前请单独确认邮箱解绑。'
    return
  }
  emit('delete', { emailId, confirm_email_binding: true })
}
</script>

<template>
  <div class="email-table">
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="emails.length === 0 && !suppressEmptyState">暂无邮箱。</p>
    <table v-else>
      <thead><tr><th>邮箱</th><th>用途</th><th>主邮箱</th><th>验证状态</th><th>授权状态</th><th v-if="canManage">操作</th></tr></thead>
      <tbody>
        <tr v-for="email in emails" :key="email.id">
          <td>{{ email.email }}</td><td>{{ displayText(EMAIL_PURPOSE_LABELS, email.purpose) }}</td><td>{{ email.is_primary ? '是' : '否' }}</td>
          <td>{{ displayText(EMAIL_VERIFICATION_LABELS, email.verification_status) }}</td><td>{{ displayText(EMAIL_AUTHORIZATION_LABELS, email.authorization_status) }}</td>
          <td v-if="canManage">
            <button class="action-button action-button--compact action-button--edit" type="button" :data-test="`edit-email-${email.id}`" @click="startEdit(email)">编辑</button>
            <button class="action-button action-button--compact action-button--danger" type="button" :data-test="`delete-email-${email.id}`" @click="startDelete(email.id)">解绑</button>
          </td>
        </tr>
      </tbody>
    </table>

    <button v-if="canManage" class="action-button action-button--create" data-test="add-email" type="button" @click="openCreate">添加邮箱</button>

    <AppModal ref="editModal" v-model="editingOpen" title="修改邮箱绑定" description="更新邮箱地址或用途，保存前需要再次确认。" :busy="busy" :dirty="() => editGuard.dirty.value" :error="dialogError">
      <form data-test="edit-email-form" class="stacked-form" novalidate @submit.prevent="update">
        <label>邮箱地址<input v-model="editForm.email" data-test="edit-email-address" type="email" required></label>
        <label>用途<select v-model="editForm.purpose"><option value="communication">通讯</option><option value="registration">注册</option><option value="backup">备用</option><option value="institutional">机构邮箱</option></select></label>
        <label><input v-model="editForm.is_primary" type="checkbox"> 主邮箱</label>
        <label class="confirmation-control"><input v-model="editForm.confirm" data-test="edit-email-confirm" type="checkbox"> 我确认此邮箱地址及绑定变更。</label>
        <div class="form-actions">
          <button class="action-button action-button--create" type="submit" :disabled="busy">保存邮箱</button>
          <button class="action-button action-button--neutral" type="button" @click="editModal?.requestClose()">取消</button>
        </div>
      </form>
    </AppModal>

    <AppConfirmDialog
      v-model="deletingOpen"
      title="解绑邮箱"
      description="解绑会将此邮箱从作者资料中移除，需单独确认。"
      confirmation-text="我确认解绑此邮箱。"
      confirm-label="确认解绑"
      :confirmed="deleteConfirmed"
      :confirm-test="`confirm-delete-${deletingId}`"
      confirmation-test="delete-email-confirm"
      :busy="busy"
      :error="dialogError"
      @update:confirmed="deleteConfirmed = $event"
      @confirm="confirmRemove"
    />

    <AppModal ref="createModal" v-model="showCreate" title="添加邮箱" description="绑定新的作者邮箱，保存前请确认地址和用途。" :busy="busy" :dirty="() => createGuard.dirty.value" :error="dialogError" @cancel="cancelCreate">
      <form data-test="create-email-form" class="stacked-form" novalidate @submit.prevent="create">
        <label>邮箱地址<input v-model="createForm.email" data-test="new-email" type="email" required></label>
        <label>用途<select v-model="createForm.purpose"><option value="communication">通讯</option><option value="registration">注册</option><option value="backup">备用</option><option value="institutional">机构邮箱</option></select></label>
        <label><input v-model="createForm.is_primary" type="checkbox"> 主邮箱</label>
        <label class="confirmation-control"><input v-model="createForm.confirm" data-test="create-email-confirm" type="checkbox"> 我确认可将此邮箱绑定到该作者。</label>
        <div class="form-actions">
          <button class="action-button action-button--create" type="submit" :disabled="busy">添加邮箱</button>
          <button class="action-button action-button--neutral" type="button" @click="createModal?.requestClose()">取消</button>
        </div>
      </form>
    </AppModal>
  </div>
</template>
