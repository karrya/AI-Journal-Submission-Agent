<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const submitting = ref(false)
const errorMessage = ref('')
const form = reactive({ current_password: '', new_password: '', confirm_password: '' })

function changePasswordError(error: unknown): string {
  const requestId = getSafeRequestId(error)
  const message = 'Unable to change password. Check your entries and try again.'
  return requestId ? `${message} Request ID: ${requestId}` : message
}

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (!form.current_password || !form.new_password || !form.confirm_password) {
      errorMessage.value = 'Complete all password fields.'
      return
    }
    if (form.new_password.length < 12 || form.new_password.length > 128) {
      errorMessage.value = 'New password must contain 12 to 128 characters.'
      return
    }
    if (form.new_password !== form.confirm_password) {
      errorMessage.value = 'Passwords do not match.'
      return
    }
    await auth.changePassword(form.current_password, form.new_password)
    await router.replace({ name: 'login' })
  } catch (error) {
    errorMessage.value = changePasswordError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-card" aria-labelledby="change-password-title">
    <p class="auth-eyebrow">First-password setup</p>
    <h1 id="change-password-title">Change password</h1>
    <p class="auth-intro">Choose a new password before using the application.</p>
    <el-alert
      v-if="errorMessage"
      class="auth-alert"
      type="error"
      :title="errorMessage"
      :closable="false"
      show-icon
    />
    <el-form
      :model="form"
      label-position="top"
      @submit.prevent="submit"
    >
      <el-form-item label="Current password" prop="current_password">
        <el-input
          v-model="form.current_password"
          data-test="current-password"
          type="password"
          autocomplete="current-password"
          show-password
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="New password" prop="new_password">
        <el-input
          v-model="form.new_password"
          data-test="new-password"
          type="password"
          autocomplete="new-password"
          show-password
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="Confirm new password" prop="confirm_password">
        <el-input
          v-model="form.confirm_password"
          data-test="confirm-password"
          type="password"
          autocomplete="new-password"
          show-password
          :disabled="submitting"
        />
      </el-form-item>
      <el-button
        class="auth-submit"
        type="primary"
        native-type="submit"
        :loading="submitting"
        :disabled="submitting"
      >
        Change password
      </el-button>
    </el-form>
  </section>
</template>
