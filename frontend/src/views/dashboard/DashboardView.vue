<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getSafeRequestId } from '../../api/client'
import { getDashboardSummary, type DashboardSummary } from '../../api/dashboard'

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
    errorMessage.value = `Unable to load the dashboard.${requestId ? ` Request ID: ${requestId}` : ''}`
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="dashboard-title">
    <h1 id="dashboard-title">Dashboard</h1>
    <p>Server-authorized submission aggregates and your recent operations.</p>
    <p v-if="loading">Loading dashboard…</p>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <template v-if="summary">
      <dl class="stat-grid" aria-label="Submission aggregates">
        <div class="stat-tile"><dt>Authorized authors</dt><dd data-test="author-count">{{ summary.author_count }}</dd></div>
        <div class="stat-tile"><dt>Manuscripts</dt><dd data-test="manuscript-count">{{ summary.manuscript_count }}</dd></div>
        <div class="stat-tile"><dt>Current-version files</dt><dd data-test="file-count">{{ summary.current_version_file_count }}</dd></div>
        <div class="stat-tile"><dt>Authorizations expiring soon</dt><dd data-test="expiring-count">{{ summary.expiring_authorization_count }}</dd></div>
      </dl>

      <section aria-labelledby="recent-operations-title">
        <h2 id="recent-operations-title">Your recent operations</h2>
        <p v-if="summary.recent_operations.length === 0">No recent operations.</p>
        <table v-else>
          <thead><tr><th>Action</th><th>Target ID</th><th>Result</th><th>Created at</th></tr></thead>
          <tbody><tr v-for="operation in summary.recent_operations" :key="`${operation.action}-${operation.created_at}-${operation.target_id}`">
            <td>{{ operation.action }}</td><td>{{ operation.target_id ?? '—' }}</td><td>{{ operation.result }}</td>
            <td><time :datetime="operation.created_at">{{ operation.created_at }}</time></td>
          </tr></tbody>
        </table>
      </section>
    </template>

    <nav class="dashboard-links" aria-label="Management pages">
      <router-link to="/manuscripts">Open manuscript workspace</router-link>
      <router-link to="/authors">Manage authors and institutions</router-link>
      <router-link to="/authorizations">Manage author authorizations</router-link>
      <router-link to="/journals">Manage publishers, platforms, and journals</router-link>
    </nav>
  </section>
</template>
