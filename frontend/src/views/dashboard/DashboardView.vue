<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getSafeRequestId } from '../../api/client'
import { getDashboardSummary, type DashboardSummary } from '../../api/dashboard'
import { AUDIT_RESULT_LABELS, displayText } from '../../utils/display'

const summary = ref<DashboardSummary | null>(null)
const loading = ref(false)
const errorMessage = ref('')

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    summary.value = await getDashboardSummary()
  } catch (error) {
    summary.value = null
    const requestId = getSafeRequestId(error)
    errorMessage.value = `无法加载工作台。${requestId ? ` 请求 ID：${requestId}` : ''}`
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="dashboard-title">
    <h1 id="dashboard-title">工作台</h1>
    <p>经服务端授权的投稿汇总和您的近期操作。</p>
    <p v-if="loading">正在加载工作台…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <template v-if="summary">
      <dl class="stat-grid" aria-label="投稿汇总">
        <div class="stat-tile"><dt>已授权作者</dt><dd data-test="author-count">{{ summary.author_count }}</dd></div>
        <div class="stat-tile"><dt>稿件</dt><dd data-test="manuscript-count">{{ summary.manuscript_count }}</dd></div>
        <div class="stat-tile"><dt>当前版本文件</dt><dd data-test="file-count">{{ summary.current_version_file_count }}</dd></div>
        <div class="stat-tile"><dt>即将到期的授权</dt><dd data-test="expiring-count">{{ summary.expiring_authorization_count }}</dd></div>
      </dl>

      <section aria-labelledby="recent-operations-title">
        <h2 id="recent-operations-title">您的近期操作</h2>
        <p v-if="summary.recent_operations.length === 0">暂无近期操作。</p>
        <table v-else>
          <thead><tr><th>操作</th><th>目标 ID</th><th>结果</th><th>创建时间</th></tr></thead>
          <tbody><tr v-for="operation in summary.recent_operations" :key="`${operation.action}-${operation.created_at}-${operation.target_id}`">
            <td>{{ operation.action }}</td><td>{{ operation.target_id ?? '—' }}</td><td>{{ displayText(AUDIT_RESULT_LABELS, operation.result) }}</td>
            <td><time :datetime="operation.created_at">{{ operation.created_at }}</time></td>
          </tr></tbody>
        </table>
      </section>
    </template>

    <nav class="dashboard-links" aria-label="管理页面">
      <router-link to="/manuscripts">进入稿件工作区</router-link>
      <router-link to="/authors">管理作者和单位</router-link>
      <router-link to="/authorizations">管理作者授权</router-link>
      <router-link to="/journals">管理出版商、平台和期刊</router-link>
    </nav>
  </section>
</template>
