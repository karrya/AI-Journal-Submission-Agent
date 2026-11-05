<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loggingOut = ref(false)
const canReadAudit = computed(() => auth.user?.roles.some(
  (role) => role === 'system_admin' || role === 'auditor',
) ?? false)

async function logout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await auth.logout().catch(() => undefined)
    await router.replace({ name: 'login' })
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <el-config-provider :locale="zhCn">
    <el-container class="app-shell">
      <el-header v-if="auth.isAuthenticated" class="app-header">
        <router-link class="app-brand" to="/dashboard">学术投稿助手</router-link>
        <nav class="app-nav" aria-label="主导航">
          <router-link to="/manuscripts">稿件</router-link>
          <router-link to="/authors">作者</router-link>
          <router-link to="/authorizations">授权</router-link>
          <router-link to="/journals">期刊</router-link>
          <router-link v-if="canReadAudit" to="/audit">审计日志</router-link>
        </nav>
        <div class="account-actions">
          <span>{{ auth.user?.display_name }}</span>
          <el-button :loading="loggingOut" :disabled="loggingOut" @click="logout">
            退出登录
          </el-button>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-config-provider>
</template>
