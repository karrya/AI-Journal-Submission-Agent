<script setup lang="ts">
import axios from 'axios'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const submitting = ref(false)
const errorMessage = ref('')
const form = reactive({ username: '', password: '' })

function safeDestination(): string {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
    ? redirect
    : '/dashboard'
}

function loginError(error: unknown): string {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  const message = status === 401
    ? 'Invalid username or password.'
    : status === 429
      ? 'Too many attempts. Please try again later.'
      : 'Unable to sign in. Please try again.'
  const requestId = getSafeRequestId(error)
  return requestId ? `${message} Request ID: ${requestId}` : message
}

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (!form.username || !form.password) {
      errorMessage.value = 'Enter your username and password.'
      return
    }
    const user = await auth.login(form.username, form.password)
    await router.replace(user.must_change_password
      ? { name: 'change-password' }
      : safeDestination())
  } catch (error) {
    errorMessage.value = loginError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-card" aria-labelledby="login-title">
    <p class="auth-eyebrow">Academic Submission Agent</p>
    <h1 id="login-title">Sign in</h1>
    <p class="auth-intro">Use your administrator account to continue.</p>
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
      <el-form-item label="Username" prop="username">
        <el-input
          v-model.trim="form.username"
          data-test="username"
          autocomplete="username"
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="Password" prop="password">
        <el-input
          v-model="form.password"
          data-test="password"
          type="password"
          autocomplete="current-password"
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
        Sign in
      </el-button>
    </el-form>
  </section>
</template>
