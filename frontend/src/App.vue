<script setup lang="ts">
import { computed, ref } from 'vue'
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
  <el-container class="app-shell">
    <el-header v-if="auth.isAuthenticated" class="app-header">
      <router-link class="app-brand" to="/dashboard">Academic Submission Agent</router-link>
      <nav class="app-nav" aria-label="Primary navigation">
        <router-link to="/manuscripts">Manuscripts</router-link>
        <router-link to="/authors">Authors</router-link>
        <router-link to="/authorizations">Authorizations</router-link>
        <router-link to="/journals">Journals</router-link>
        <router-link v-if="canReadAudit" to="/audit">Audit logs</router-link>
      </nav>
      <div class="account-actions">
        <span>{{ auth.user?.display_name }}</span>
        <el-button :loading="loggingOut" :disabled="loggingOut" @click="logout">
          Sign out
        </el-button>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>
