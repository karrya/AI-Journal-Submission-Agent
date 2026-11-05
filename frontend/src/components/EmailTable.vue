<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { EmailCreate, EmailResponse, EmailUpdate } from '../api/authors'

withDefaults(defineProps<{
  emails: EmailResponse[]
  canManage?: boolean
  busy?: boolean
}>(), {
  canManage: false,
  busy: false,
})

const emit = defineEmits<{
  create: [payload: EmailCreate]
  update: [change: { emailId: string; payload: EmailUpdate }]
  delete: [change: { emailId: string; confirm_email_binding: true }]
}>()

const createForm = reactive({
  email: '',
  purpose: 'communication' as 'communication' | 'registration' | 'backup',
  is_primary: false,
  confirm: false,
})
const editForm = reactive({
  email: '',
  purpose: 'communication' as 'communication' | 'registration' | 'backup',
  is_primary: false,
  confirm: false,
})
const editingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)
const deleteConfirmed = ref(false)
const errorMessage = ref('')

function create(): void {
  errorMessage.value = ''
  if (!createForm.email.trim()) {
    errorMessage.value = 'Email address is required.'
    return
  }
  if (!createForm.confirm) {
    errorMessage.value = 'Confirm the email binding before saving.'
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
  editingId.value = email.id
  deletingId.value = null
  Object.assign(editForm, {
    email: email.email,
    purpose: email.purpose,
    is_primary: email.is_primary,
    confirm: false,
  })
  errorMessage.value = ''
}

function update(): void {
  if (!editingId.value) return
  errorMessage.value = ''
  if (!editForm.email.trim()) {
    errorMessage.value = 'Email address is required.'
    return
  }
  if (!editForm.confirm) {
    errorMessage.value = 'Confirm the email binding before saving changes.'
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
  deletingId.value = emailId
  editingId.value = null
  deleteConfirmed.value = false
  errorMessage.value = ''
}

function remove(emailId: string): void {
  if (!deleteConfirmed.value) {
    errorMessage.value = 'Confirm the email unbinding separately before deleting.'
    return
  }
  emit('delete', { emailId, confirm_email_binding: true })
}
</script>

<template>
  <div class="email-table">
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="emails.length === 0">No emails.</p>
    <table v-else>
      <thead><tr><th>Email</th><th>Purpose</th><th>Primary</th><th>Verification</th><th>Authorization</th><th v-if="canManage">Actions</th></tr></thead>
      <tbody>
        <tr v-for="email in emails" :key="email.id">
          <td>{{ email.email }}</td><td>{{ email.purpose }}</td><td>{{ email.is_primary ? 'Yes' : 'No' }}</td>
          <td>{{ email.verification_status }}</td><td>{{ email.authorization_status }}</td>
          <td v-if="canManage">
            <button type="button" :data-test="`edit-email-${email.id}`" @click="startEdit(email)">Edit</button>
            <button type="button" :data-test="`delete-email-${email.id}`" @click="startDelete(email.id)">Unbind</button>
          </td>
        </tr>
      </tbody>
    </table>

    <form v-if="editingId" data-test="edit-email-form" class="stacked-form" novalidate @submit.prevent="update">
      <h3>Change email binding</h3>
      <label>Email address<input v-model="editForm.email" data-test="edit-email-address" type="email" required></label>
      <label>Purpose<select v-model="editForm.purpose"><option value="communication">Communication</option><option value="registration">Registration</option><option value="backup">Backup</option></select></label>
      <label><input v-model="editForm.is_primary" type="checkbox"> Primary email</label>
      <label class="confirmation-control"><input v-model="editForm.confirm" data-test="edit-email-confirm" type="checkbox"> I confirm this email address and binding change.</label>
      <button type="submit">Save email</button>
      <button type="button" @click="editingId = null">Cancel</button>
    </form>

    <section v-if="deletingId" class="confirmation-panel" aria-label="Confirm email unbinding">
      <p>Unbinding removes this email from the author. This requires separate confirmation.</p>
      <label class="confirmation-control"><input v-model="deleteConfirmed" data-test="delete-email-confirm" type="checkbox"> I confirm this email unbinding.</label>
      <button type="button" :data-test="`confirm-delete-${deletingId}`" @click="remove(deletingId)">Confirm unbinding</button>
      <button type="button" @click="deletingId = null">Cancel</button>
    </section>

    <form v-if="canManage" data-test="create-email-form" class="stacked-form" novalidate @submit.prevent="create">
      <h3>Add email</h3>
      <label>Email address<input v-model="createForm.email" data-test="new-email" type="email" required></label>
      <label>Purpose<select v-model="createForm.purpose"><option value="communication">Communication</option><option value="registration">Registration</option><option value="backup">Backup</option></select></label>
      <label><input v-model="createForm.is_primary" type="checkbox"> Primary email</label>
      <label class="confirmation-control"><input v-model="createForm.confirm" data-test="create-email-confirm" type="checkbox"> I confirm that this email may be bound to the author.</label>
      <button type="submit" :disabled="busy">Add email</button>
    </form>
  </div>
</template>
