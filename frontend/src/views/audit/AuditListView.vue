<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getAuditLog, listAuditLogs, type AuditCategory, type AuditListQuery, type AuditLog } from '../../api/audit'
import { getSafeRequestId } from '../../api/client'
import type { SortOrder } from '../../api/authors'
import {
  AUDIT_ACTOR_LABELS,
  AUDIT_CATEGORY_LABELS,
  AUDIT_RESULT_LABELS,
  AUDIT_TARGET_LABELS,
  displayText,
} from '../../utils/display'

const logs = ref<AuditLog[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const detail = ref<AuditLog | null>(null)
const detailLoading = ref(false)
let loadSequence = 0

const filters = reactive({
  page: 1,
  page_size: 20,
  actor_user_id: '', author_id: '', category: '' as AuditCategory | '', action: '',
  target_type: '', target_id: '', result: '' as 'success' | 'failure' | '', request_id: '',
  created_from: '', created_to: '', sort: 'created_at' as const, order: 'desc' as SortOrder,
})

function trimmed(value: string): string | undefined {
  return value.trim() || undefined
}

function isoDateTime(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  detail.value = null
  detailLoading.value = false
  const query: AuditListQuery = {
    page: filters.page,
    page_size: filters.page_size,
    actor_user_id: trimmed(filters.actor_user_id),
    author_id: trimmed(filters.author_id),
    category: filters.category || undefined,
    action: trimmed(filters.action),
    target_type: trimmed(filters.target_type),
    target_id: trimmed(filters.target_id),
    result: filters.result || undefined,
    request_id: trimmed(filters.request_id),
    created_from: isoDateTime(filters.created_from),
    created_to: isoDateTime(filters.created_to),
    sort: filters.sort,
    order: filters.order,
  }
  try {
    const result = await listAuditLogs(query)
    if (sequence !== loadSequence) return
    logs.value = result.items
    total.value = result.total
  } catch (error) {
    if (sequence !== loadSequence) return
    logs.value = []
    total.value = 0
    errorMessage.value = safeError(error, '无法加载审计日志。')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function applyFilters(): void {
  filters.page = 1
  void load()
}

function changePage(page: number): void {
  if (loading.value || page < 1 || (page - 1) * filters.page_size >= total.value) return
  filters.page = page
  void load()
}

async function showDetail(logId: string): Promise<void> {
  if (detailLoading.value) return
  const sequence = loadSequence
  detailLoading.value = true
  errorMessage.value = ''
  try {
    const result = await getAuditLog(logId)
    if (sequence === loadSequence) detail.value = result
  } catch (error) {
    if (sequence === loadSequence) {
      errorMessage.value = safeError(error, '无法加载审计日志详情。')
    }
  } finally {
    if (sequence === loadSequence) detailLoading.value = false
  }
}

function formatSummary(value: Record<string, unknown> | null | undefined): string {
  return value == null ? '—' : JSON.stringify(value, null, 2)
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="audit-list-title">
    <h1 id="audit-list-title">审计日志</h1>
    <p>只读操作历史，审计记录不可编辑或删除。</p>

    <form class="stacked-form" aria-label="审计筛选条件" @submit.prevent="applyFilters">
      <div class="form-grid">
        <label>操作用户 ID<input v-model="filters.actor_user_id" data-test="audit-actor"></label>
        <label>作者 ID<input v-model="filters.author_id"></label>
        <label>类别
          <select v-model="filters.category" data-test="audit-category">
            <option value="">全部类别</option>
            <option value="authentication">身份认证</option>
            <option value="authorization">授权</option>
            <option value="business">业务操作</option>
            <option value="sensitive_access">敏感访问</option>
          </select>
        </label>
        <label>操作<input v-model="filters.action" data-test="audit-action"></label>
        <label>目标类型<input v-model="filters.target_type"></label>
        <label>目标 ID<input v-model="filters.target_id"></label>
        <label>结果
          <select v-model="filters.result" data-test="audit-result">
            <option value="">全部结果</option><option value="success">成功</option><option value="failure">失败</option>
          </select>
        </label>
        <label>请求 ID<input v-model="filters.request_id"></label>
        <label>创建时间从<input v-model="filters.created_from" data-test="audit-created-from" type="datetime-local"></label>
        <label>创建时间至<input v-model="filters.created_to" type="datetime-local"></label>
        <label>排序
          <select v-model="filters.order"><option value="desc">最新优先</option><option value="asc">最早优先</option></select>
        </label>
      </div>
      <button type="button" data-test="apply-audit-filters" @click="applyFilters">应用筛选</button>
    </form>

    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="loading">正在加载审计日志…</p>
    <p v-else-if="!errorMessage && logs.length === 0">未找到审计日志。</p>
    <table v-else>
      <thead><tr><th>创建时间</th><th>操作者</th><th>类别</th><th>操作</th><th>目标</th><th>结果</th><th>请求 ID</th><th>详情</th></tr></thead>
      <tbody><tr v-for="log in logs" :key="log.id">
        <td><time :datetime="log.created_at">{{ log.created_at }}</time></td>
        <td>{{ log.actor_user_id ?? displayText(AUDIT_ACTOR_LABELS, log.actor_type) }}</td><td>{{ displayText(AUDIT_CATEGORY_LABELS, log.category) }}</td><td>{{ log.action }}</td>
        <td>{{ log.target_type ? displayText(AUDIT_TARGET_LABELS, log.target_type) : '—' }}<br>{{ log.target_id ?? '—' }}</td><td>{{ displayText(AUDIT_RESULT_LABELS, log.result) }}</td><td>{{ log.request_id }}</td>
        <td><button type="button" :data-test="`view-audit-${log.id}`" :disabled="detailLoading" @click="showDetail(log.id)">查看详情</button></td>
      </tr></tbody>
    </table>

    <section v-if="detail" data-test="audit-detail" aria-labelledby="audit-detail-title">
      <h2 id="audit-detail-title">审计详情</h2>
      <dl class="detail-grid">
        <div><dt>日志 ID</dt><dd>{{ detail.id }}</dd></div>
        <div><dt>操作用户 ID</dt><dd>{{ detail.actor_user_id ?? '—' }}</dd></div>
        <div><dt>作者 ID</dt><dd>{{ detail.author_id ?? '—' }}</dd></div>
        <div><dt>操作</dt><dd>{{ detail.action }}</dd></div>
        <div><dt>结果</dt><dd>{{ displayText(AUDIT_RESULT_LABELS, detail.result) }}</dd></div>
        <div><dt>错误代码</dt><dd>{{ detail.error_code ?? '—' }}</dd></div>
        <div><dt>错误信息</dt><dd>{{ detail.error_message ?? '—' }}</dd></div>
      </dl>
      <h3>变更前摘要</h3><pre>{{ formatSummary(detail.before_summary) }}</pre>
      <h3>变更后摘要</h3><pre>{{ formatSummary(detail.after_summary) }}</pre>
    </section>

    <nav class="pagination" aria-label="审计日志分页">
      <button type="button" :disabled="filters.page === 1 || loading" @click="changePage(filters.page - 1)">上一页</button>
      <span>第 {{ filters.page }} 页 · 共 {{ total }} 条</span>
      <button type="button" data-test="next-audit" :disabled="filters.page * filters.page_size >= total || loading" @click="changePage(filters.page + 1)">下一页</button>
    </nav>
  </section>
</template>
