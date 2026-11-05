<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getAuditLog, listAuditLogs, type AuditCategory, type AuditListQuery, type AuditLog } from '../../api/audit'
import { getSafeRequestId } from '../../api/client'
import type { SortOrder } from '../../api/authors'

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
  return requestId ? `${fallback} Request ID: ${requestId}` : fallback
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
    errorMessage.value = safeError(error, 'Unable to load audit logs.')
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
      errorMessage.value = safeError(error, 'Unable to load the audit log detail.')
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
    <h1 id="audit-list-title">Audit logs</h1>
    <p>Read-only operation history. Audit records cannot be edited or deleted.</p>

    <form class="stacked-form" aria-label="Audit filters" @submit.prevent="applyFilters">
      <div class="form-grid">
        <label>Actor user ID<input v-model="filters.actor_user_id" data-test="audit-actor"></label>
        <label>Author ID<input v-model="filters.author_id"></label>
        <label>Category
          <select v-model="filters.category" data-test="audit-category">
            <option value="">All categories</option>
            <option value="authentication">Authentication</option>
            <option value="authorization">Authorization</option>
            <option value="business">Business</option>
            <option value="sensitive_access">Sensitive access</option>
          </select>
        </label>
        <label>Action<input v-model="filters.action" data-test="audit-action"></label>
        <label>Target type<input v-model="filters.target_type"></label>
        <label>Target ID<input v-model="filters.target_id"></label>
        <label>Result
          <select v-model="filters.result" data-test="audit-result">
            <option value="">All results</option><option value="success">Success</option><option value="failure">Failure</option>
          </select>
        </label>
        <label>Request ID<input v-model="filters.request_id"></label>
        <label>Created from<input v-model="filters.created_from" data-test="audit-created-from" type="datetime-local"></label>
        <label>Created to<input v-model="filters.created_to" type="datetime-local"></label>
        <label>Order
          <select v-model="filters.order"><option value="desc">Newest first</option><option value="asc">Oldest first</option></select>
        </label>
      </div>
      <button type="button" data-test="apply-audit-filters" @click="applyFilters">Apply filters</button>
    </form>

    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="loading">Loading audit logs…</p>
    <p v-else-if="!errorMessage && logs.length === 0">No audit logs found.</p>
    <table v-else>
      <thead><tr><th>Created at</th><th>Actor</th><th>Category</th><th>Action</th><th>Target</th><th>Result</th><th>Request ID</th><th>Detail</th></tr></thead>
      <tbody><tr v-for="log in logs" :key="log.id">
        <td><time :datetime="log.created_at">{{ log.created_at }}</time></td>
        <td>{{ log.actor_user_id ?? log.actor_type }}</td><td>{{ log.category }}</td><td>{{ log.action }}</td>
        <td>{{ log.target_type ?? '—' }}<br>{{ log.target_id ?? '—' }}</td><td>{{ log.result }}</td><td>{{ log.request_id }}</td>
        <td><button type="button" :data-test="`view-audit-${log.id}`" :disabled="detailLoading" @click="showDetail(log.id)">View detail</button></td>
      </tr></tbody>
    </table>

    <section v-if="detail" data-test="audit-detail" aria-labelledby="audit-detail-title">
      <h2 id="audit-detail-title">Audit detail</h2>
      <dl class="detail-grid">
        <div><dt>Log ID</dt><dd>{{ detail.id }}</dd></div>
        <div><dt>Actor user ID</dt><dd>{{ detail.actor_user_id ?? '—' }}</dd></div>
        <div><dt>Author ID</dt><dd>{{ detail.author_id ?? '—' }}</dd></div>
        <div><dt>Action</dt><dd>{{ detail.action }}</dd></div>
        <div><dt>Result</dt><dd>{{ detail.result }}</dd></div>
        <div><dt>Error code</dt><dd>{{ detail.error_code ?? '—' }}</dd></div>
        <div><dt>Error message</dt><dd>{{ detail.error_message ?? '—' }}</dd></div>
      </dl>
      <h3>Before summary</h3><pre>{{ formatSummary(detail.before_summary) }}</pre>
      <h3>After summary</h3><pre>{{ formatSummary(detail.after_summary) }}</pre>
    </section>

    <nav class="pagination" aria-label="Audit pages">
      <button type="button" :disabled="filters.page === 1 || loading" @click="changePage(filters.page - 1)">Previous</button>
      <span>Page {{ filters.page }} · {{ total }} total</span>
      <button type="button" data-test="next-audit" :disabled="filters.page * filters.page_size >= total || loading" @click="changePage(filters.page + 1)">Next</button>
    </nav>
  </section>
</template>
