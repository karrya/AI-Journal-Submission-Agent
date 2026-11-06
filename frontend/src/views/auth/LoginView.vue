<script setup lang="ts">
import axios from 'axios'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSafeRequestId } from '../../api/client'
import AuthShell from '../../components/AuthShell.vue'
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
    ? '用户名或密码错误。'
    : status === 429
      ? '尝试次数过多，请稍后重试。'
      : '无法登录，请重试。'
  const requestId = getSafeRequestId(error)
  return requestId ? `${message} 请求 ID：${requestId}` : message
}

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (!form.username || !form.password) {
      errorMessage.value = '请输入用户名和密码。'
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
  <AuthShell>
    <section class="auth-card" aria-labelledby="login-title">
      <p class="auth-eyebrow">欢迎回来</p>
      <h1 id="login-title">登录工作区</h1>
      <p class="auth-intro">登录您的账号，继续管理研究与投稿。</p>
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
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model.trim="form.username"
          data-test="username"
          autocomplete="username"
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="密码" prop="password">
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
        登录
      </el-button>
    </el-form>
    </section>
  </AuthShell>
</template>
