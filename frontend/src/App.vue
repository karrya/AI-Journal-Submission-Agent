<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import AppLogo from './components/AppLogo.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loggingOut = ref(false)
const canReadAudit = computed(() => auth.user?.roles.some(
  (role) => role === 'system_admin' || role === 'auditor',
) ?? false)
const navigation = [
  { to: '/dashboard', label: '工作台', icon: 'dashboard' },
  { to: '/manuscripts', label: '稿件管理', icon: 'manuscripts' },
  { to: '/authors', label: '作者与单位', icon: 'authors' },
  { to: '/authorizations', label: '作者授权', icon: 'authorizations' },
  { to: '/journals', label: '期刊管理', icon: 'journals' },
]

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
      <aside v-if="auth.isAuthenticated" class="app-sidebar">
        <div class="sidebar-glow" aria-hidden="true" />
        <router-link class="app-brand" to="/dashboard" aria-label="学术投稿助手工作台">
          <AppLogo :size="44" />
          <span class="app-brand-copy">
            <strong>学术投稿助手</strong>
            <small>ACADEMIC SUBMISSION</small>
          </span>
        </router-link>

        <p class="sidebar-section-label">工作空间</p>
        <nav class="app-nav" aria-label="主导航">
          <router-link v-for="item in navigation" :key="item.to" :to="item.to" class="app-nav-link">
            <AppIcon :name="item.icon" />
            <span>{{ item.label }}</span>
            <span class="nav-active-dot" aria-hidden="true" />
          </router-link>
          <router-link v-if="canReadAudit" to="/audit" class="app-nav-link">
            <AppIcon name="audit" />
            <span>审计日志</span>
            <span class="nav-active-dot" aria-hidden="true" />
          </router-link>
        </nav>

        <div class="sidebar-note">
          <span class="sidebar-note-eyebrow">RESEARCH WORKSPACE</span>
          <p>让投稿流程更清晰，<br>让研究价值被看见。</p>
          <span class="sidebar-note-line" aria-hidden="true" />
        </div>

        <div class="account-actions">
          <div class="account-profile">
            <span class="account-avatar" aria-hidden="true">{{ auth.user?.display_name.slice(0, 1).toUpperCase() }}</span>
            <span class="account-copy">
              <strong>{{ auth.user?.display_name }}</strong>
              <small>本地学术工作区</small>
            </span>
          </div>
          <button class="logout-button" type="button" :disabled="loggingOut" aria-label="退出登录" @click="logout">
            <AppIcon name="logout" />
            <span>{{ loggingOut ? '正在退出…' : '退出登录' }}</span>
          </button>
        </div>
      </aside>

      <el-main class="app-main" :class="{ 'app-main--authenticated': auth.isAuthenticated }">
        <div v-if="auth.isAuthenticated" class="app-ambient" aria-hidden="true" />
        <router-view />
      </el-main>
    </el-container>
  </el-config-provider>
</template>
