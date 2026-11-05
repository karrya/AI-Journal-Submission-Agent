<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loggingOut = ref(false)

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
