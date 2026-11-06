<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getSafeRequestId } from '../../api/client'
import { getDashboardSummary, type DashboardSummary } from '../../api/dashboard'
import AppIcon from '../../components/AppIcon.vue'
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
  <section class="management-page dashboard-page" aria-labelledby="dashboard-title">
    <header class="page-hero">
      <div>
        <p class="page-eyebrow">ACADEMIC WORKSPACE</p>
        <h1 id="dashboard-title">工作台</h1>
        <p>汇集您的投稿进展与近期操作，让每一步都清晰可见。</p>
      </div>
      <span class="page-hero-badge"><i aria-hidden="true" />投稿数据概览</span>
    </header>

    <p v-if="loading" class="loading-state">正在加载工作台<span class="loading-dots" aria-hidden="true">…</span></p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <dl v-if="summary" class="stat-grid" aria-label="投稿汇总">
      <div class="stat-tile">
        <dt><span>已授权作者<small>AUTHORS</small></span><span class="stat-icon"><AppIcon name="authors" /></span></dt>
        <dd class="stat-value" data-test="author-count">{{ summary.author_count }}</dd>
        <dd class="stat-caption">当前可管理的作者</dd>
      </div>
      <div class="stat-tile">
        <dt><span>稿件<small>MANUSCRIPTS</small></span><span class="stat-icon"><AppIcon name="manuscripts" /></span></dt>
        <dd class="stat-value" data-test="manuscript-count">{{ summary.manuscript_count }}</dd>
        <dd class="stat-caption">授权范围内的全部稿件</dd>
      </div>
      <div class="stat-tile">
        <dt><span>当前版本文件<small>CURRENT FILES</small></span><span class="stat-icon"><AppIcon name="files" /></span></dt>
        <dd class="stat-value" data-test="file-count">{{ summary.current_version_file_count }}</dd>
        <dd class="stat-caption">当前稿件版本关联文件</dd>
      </div>
      <div class="stat-tile stat-tile--warning">
        <dt><span>即将到期授权<small>EXPIRING SOON</small></span><span class="stat-icon"><AppIcon name="clock" /></span></dt>
        <dd class="stat-value" data-test="expiring-count">{{ summary.expiring_authorization_count }}</dd>
        <dd class="stat-caption">建议及时检查与处理</dd>
      </div>
    </dl>

    <div class="dashboard-content-grid">
      <section v-if="summary" class="recent-operations" aria-labelledby="recent-operations-title">
        <div class="section-heading">
          <div>
            <p class="section-kicker">ACTIVITY</p>
            <h2 id="recent-operations-title">近期操作</h2>
          </div>
          <span class="section-badge">仅显示本人</span>
        </div>
        <p v-if="summary.recent_operations.length === 0" class="empty-state">暂无近期操作。</p>
        <div v-else class="table-shell">
          <table>
            <thead><tr><th>操作</th><th>目标 ID</th><th>结果</th><th>创建时间</th></tr></thead>
            <tbody><tr v-for="operation in summary.recent_operations" :key="`${operation.action}-${operation.created_at}-${operation.target_id}`">
              <td><span class="operation-action">{{ operation.action }}</span></td>
              <td class="mono-cell">{{ operation.target_id ?? '—' }}</td>
              <td><span class="result-label" :class="`result-label--${operation.result}`">{{ displayText(AUDIT_RESULT_LABELS, operation.result) }}</span></td>
              <td><time :datetime="operation.created_at">{{ operation.created_at }}</time></td>
            </tr></tbody>
          </table>
        </div>
      </section>

      <nav class="dashboard-links" aria-label="管理页面">
        <p class="section-kicker">QUICK ACCESS</p>
        <h2>快捷入口</h2>
        <router-link to="/manuscripts">
          <span class="quick-link-icon"><AppIcon name="manuscripts" /></span>
          <span class="quick-link-copy"><strong>稿件工作区</strong><small>管理稿件、版本与文件</small></span>
          <AppIcon name="arrow" />
        </router-link>
        <router-link to="/authors">
          <span class="quick-link-icon"><AppIcon name="authors" /></span>
          <span class="quick-link-copy"><strong>作者与单位</strong><small>维护作者档案及单位信息</small></span>
          <AppIcon name="arrow" />
        </router-link>
        <router-link to="/authorizations">
          <span class="quick-link-icon"><AppIcon name="authorizations" /></span>
          <span class="quick-link-copy"><strong>作者授权</strong><small>查看和管理访问范围</small></span>
          <AppIcon name="arrow" />
        </router-link>
        <router-link to="/journals">
          <span class="quick-link-icon"><AppIcon name="journals" /></span>
          <span class="quick-link-copy"><strong>期刊管理</strong><small>浏览出版商、平台与期刊</small></span>
          <AppIcon name="arrow" />
        </router-link>
      </nav>
    </div>
  </section>
</template>
