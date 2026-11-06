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
  const message = '无法修改密码，请检查输入后重试。'
  return requestId ? `${message} 请求 ID：${requestId}` : message
}

async function submit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (!form.current_password || !form.new_password || !form.confirm_password) {
      errorMessage.value = '请填写所有密码字段。'
      return
    }
    if (form.new_password.length < 6 || form.new_password.length > 128) {
      errorMessage.value = '新密码长度须为 6 至 128 个字符。'
      return
    }
    if (form.new_password !== form.confirm_password) {
      errorMessage.value = '两次输入的密码不一致。'
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
    <p class="auth-eyebrow">首次密码设置</p>
    <h1 id="change-password-title">修改密码</h1>
    <p class="auth-intro">请先设置新密码，再使用本系统。</p>
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
      <el-form-item label="当前密码" prop="current_password">
        <el-input
          v-model="form.current_password"
          data-test="current-password"
          type="password"
          autocomplete="current-password"
          show-password
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="新密码" prop="new_password">
        <el-input
          v-model="form.new_password"
          data-test="new-password"
          type="password"
          autocomplete="new-password"
          show-password
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item label="确认新密码" prop="confirm_password">
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
        修改密码
      </el-button>
    </el-form>
  </section>
</template>
