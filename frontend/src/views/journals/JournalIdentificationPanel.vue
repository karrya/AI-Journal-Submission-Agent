<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  cancelDiscoveryTask,
  confirmIdentity,
  confirmTaskCandidate,
  getDiscoveryTask,
  getJournalOptions,
  getPublisherOptions,
  identifyJournal,
  retryDiscoveryTask,
  type DiscoveryCandidate,
  type DiscoveryTask,
  type IdentifyResponse,
  type JournalOption,
  type PublisherOption,
} from '../../api/identification'
import { getSafeRequestId } from '../../api/client'
import { showSaveSuccess } from '../../utils/feedback'
import { safeResourceUrl } from '../../utils/url'

const form = reactive({
  publisher_name: '',
  journal_name: '',
  issn: '',
  eissn: '',
  website_url: '',
  article_type: '',
})
const activeTask = ref<DiscoveryTask | null>(null)
const candidates = ref<DiscoveryCandidate[]>([])
const selectedCandidateKey = ref('')
const identified = ref(false)
const identifying = ref(false)
const confirming = ref(false)
const cancelling = ref(false)
const retrying = ref(false)
const errorMessage = ref('')
const confirmationNote = ref('')
const publisherOptions = ref<PublisherOption[]>([])
const journalOptions = ref<JournalOption[]>([])
const selectedPublisherId = ref('')
const publisherCustomMode = ref(false)
const CUSTOM_PUBLISHER_VALUE = '__manual_publisher__'
let journalTimer: ReturnType<typeof setTimeout> | undefined
let taskTimer: ReturnType<typeof setTimeout> | undefined
let publisherSequence = 0
let journalSequence = 0
let taskSequence = 0
let operationSequence = 0
let mounted = true

const taskStatus = computed(() => activeTask.value?.status ?? '')
const taskProgress = computed(() => activeTask.value?.progress ?? 0)
const taskWarnings = computed(() => activeTask.value?.warnings ?? [])
const isTaskRunning = computed(() => ['PENDING', 'PROCESSING'].includes(taskStatus.value))
const isTerminal = computed(() => ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(taskStatus.value))
const canRetry = computed(() => Boolean(
  activeTask.value
  && !retrying.value
  && (
    (taskStatus.value === 'FAILED' && activeTask.value.retryable)
    || ['SUCCEEDED', 'CANCELLED'].includes(taskStatus.value)
  )
))
const canConfirm = computed(() => Boolean(
  selectedCandidateKey.value
  && activeTask.value
  && taskStatus.value === 'SUCCEEDED'
  && !activeTask.value.journal_id
  && !confirming.value
  && candidates.value.some((candidate) => (
    candidateKey(candidate) === selectedCandidateKey.value
    && ['UNVERIFIED', 'NEEDS_CONFIRMATION', 'UNKNOWN'].includes(candidate.identity_status)
  ))
))

function candidateKey(candidate: DiscoveryCandidate): string {
  return candidate.candidate_key ?? candidate.id ?? ''
}

function applyTask(task: DiscoveryTask): void {
  activeTask.value = task
  candidates.value = task.candidates
  identified.value = true
}

function taskFromIdentifyResponse(result: IdentifyResponse): DiscoveryTask {
  return {
    task_id: result.task_id,
    task_type: 'journal.identify',
    status: result.status,
    progress: result.status === 'SUCCEEDED' ? 100 : 0,
    message: null,
    warnings: [],
    journal_id: result.journal_id ?? null,
    candidates: result.candidates,
  }
}

function stopTaskPolling(): void {
  taskSequence += 1
  if (taskTimer) clearTimeout(taskTimer)
  taskTimer = undefined
}

async function pollTask(taskId: string, sequence: number): Promise<void> {
  try {
    const result = await getDiscoveryTask(taskId)
    if (sequence !== taskSequence || !mounted) return
    applyTask(result)
    if (['PENDING', 'PROCESSING'].includes(result.status)) {
      taskTimer = setTimeout(() => void pollTask(taskId, sequence), 1000)
    }
  } catch (error) {
    if (sequence !== taskSequence || !mounted) return
    errorMessage.value = errorText(error, '无法查询识别任务进度。')
    if (isTaskRunning.value) {
      taskTimer = setTimeout(() => void pollTask(taskId, sequence), 2000)
    }
  }
}

function startTaskPolling(taskId: string): void {
  if (!mounted) return
  stopTaskPolling()
  void pollTask(taskId, taskSequence)
}

function clearJournalSelection(clearValues = true): void {
  selectedPublisherId.value = ''
  journalOptions.value = []
  if (clearValues) {
    form.journal_name = ''
    form.issn = ''
    form.eissn = ''
    form.website_url = ''
  }
}

async function loadPublisherOptions(query: string): Promise<void> {
  const sequence = ++publisherSequence
  try {
    const result = await getPublisherOptions(query)
    if (sequence !== publisherSequence) return
    publisherOptions.value = result
    const selected = result.find((publisher) => publisher.name === form.publisher_name.trim())
    if (!selected) {
      selectedPublisherId.value = ''
      return
    }
    selectedPublisherId.value = selected.id
    await loadJournalOptions('')
  } catch (error) {
    if (sequence === publisherSequence) errorMessage.value = errorText(error, '无法加载出版社选项。')
  }
}

function handlePublisherChange(): void {
  const hadPublisher = Boolean(selectedPublisherId.value)
  if (form.publisher_name === CUSTOM_PUBLISHER_VALUE) {
    publisherCustomMode.value = true
    form.publisher_name = ''
    clearJournalSelection(hadPublisher)
    return
  }
  clearJournalSelection(hadPublisher)
  const selected = publisherOptions.value.find((publisher) => (
    publisher.name === form.publisher_name.trim()
  ))
  selectedPublisherId.value = selected?.id ?? ''
  if (selected) void loadJournalOptions('')
}

function showExistingPublisherOptions(): void {
  publisherCustomMode.value = false
  form.publisher_name = ''
  clearJournalSelection(true)
  void loadPublisherOptions('')
}

function autofillJournalIdentifiers(): void {
  const selected = journalOptions.value.find((journal) => (
    journal.name === form.journal_name.trim() && journal.publisher_id === selectedPublisherId.value
  ))
  if (!selected) return
  if (!form.issn) form.issn = selected.issn ?? ''
  if (!form.eissn) form.eissn = selected.eissn ?? ''
  if (!form.website_url) form.website_url = selected.website_url ?? ''
}

async function loadJournalOptions(query: string): Promise<void> {
  const publisherId = selectedPublisherId.value
  if (!publisherId) {
    journalOptions.value = []
    return
  }
  const sequence = ++journalSequence
  try {
    const result = await getJournalOptions(publisherId, query)
    if (sequence !== journalSequence || publisherId !== selectedPublisherId.value) return
    journalOptions.value = result
    autofillJournalIdentifiers()
  } catch (error) {
    if (sequence === journalSequence) errorMessage.value = errorText(error, '无法加载期刊选项。')
  }
}

function handleJournalInput(): void {
  form.issn = ''
  form.eissn = ''
  form.website_url = ''
  autofillJournalIdentifiers()
  if (journalTimer) clearTimeout(journalTimer)
  const query = form.journal_name.trim()
  journalTimer = setTimeout(() => void loadJournalOptions(query), 250)
}

function clearIdentification(): void {
  operationSequence += 1
  stopTaskPolling()
  if (journalTimer) clearTimeout(journalTimer)
  journalTimer = undefined
  publisherSequence += 1
  journalSequence += 1
  form.publisher_name = ''
  form.journal_name = ''
  form.issn = ''
  form.eissn = ''
  form.website_url = ''
  form.article_type = ''
  publisherCustomMode.value = false
  publisherOptions.value = []
  journalOptions.value = []
  selectedPublisherId.value = ''
  activeTask.value = null
  candidates.value = []
  selectedCandidateKey.value = ''
  identified.value = false
  confirmationNote.value = ''
  errorMessage.value = ''
  void loadPublisherOptions('')
}

onMounted(() => {
  mounted = true
  void loadPublisherOptions('')
})
onUnmounted(() => {
  mounted = false
  operationSequence += 1
  stopTaskPolling()
  if (journalTimer) clearTimeout(journalTimer)
})

function optional(value: string): string | undefined {
  const trimmed = value.trim()
  return trimmed || undefined
}

function errorText(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  const responseMessage = (error as { response?: { data?: { message?: string } } }).response?.data?.message
  const message = responseMessage ?? fallback
  return requestId ? `${message} 请求 ID：${requestId}` : message
}

async function identify(): Promise<void> {
  if (identifying.value) return
  errorMessage.value = ''
  if (!form.journal_name.trim()) {
    errorMessage.value = '请填写期刊名称。'
    return
  }
  identifying.value = true
  identified.value = false
  selectedCandidateKey.value = ''
  candidates.value = []
  activeTask.value = null
  stopTaskPolling()
  const operation = operationSequence
  try {
    const result = await identifyJournal({
      publisher_name: optional(form.publisher_name),
      journal_name: form.journal_name.trim(),
      issn: optional(form.issn),
      eissn: optional(form.eissn),
      website_url: optional(form.website_url),
      article_type: optional(form.article_type),
    })
    if (operation !== operationSequence || !mounted) return
    const task = taskFromIdentifyResponse(result)
    applyTask(task)
    if (['PENDING', 'PROCESSING'].includes(task.status)) startTaskPolling(task.task_id)
  } catch (error) {
    errorMessage.value = errorText(error, '无法创建网络识别任务。')
  } finally {
    identifying.value = false
  }
}

async function cancelActiveTask(): Promise<void> {
  if (!activeTask.value || cancelling.value) return
  cancelling.value = true
  errorMessage.value = ''
  const operation = operationSequence
  try {
    const result = await cancelDiscoveryTask(activeTask.value.task_id)
    if (operation !== operationSequence || !mounted) return
    applyTask(result)
    if (['PENDING', 'PROCESSING'].includes(result.status)) startTaskPolling(result.task_id)
    else stopTaskPolling()
  } catch (error) {
    errorMessage.value = errorText(error, '无法取消识别任务。')
  } finally {
    cancelling.value = false
  }
}

async function retryActiveTask(): Promise<void> {
  if (!activeTask.value || retrying.value) return
  retrying.value = true
  errorMessage.value = ''
  const operation = operationSequence
  try {
    const result = await retryDiscoveryTask(activeTask.value.task_id)
    if (operation !== operationSequence || !mounted) return
    applyTask(result)
    startTaskPolling(result.task_id)
  } catch (error) {
    errorMessage.value = errorText(error, '无法重试识别任务。')
  } finally {
    retrying.value = false
  }
}

async function confirmSelected(): Promise<void> {
  if (!canConfirm.value) return
  const selected = candidates.value.find((candidate) => (
    candidateKey(candidate) === selectedCandidateKey.value
  ))
  if (!selected) return
  confirming.value = true
  errorMessage.value = ''
  const operation = operationSequence
  try {
    if (selected.candidate_key && activeTask.value) {
      const result = await confirmTaskCandidate(
        activeTask.value.task_id,
        selected.candidate_key,
        confirmationNote.value.trim() || undefined,
      )
      if (operation !== operationSequence || !mounted) return
      applyTask(result)
    } else if (selected.id && selected.updated_at) {
      const result = await confirmIdentity(
        selected.id,
        selected.updated_at,
        confirmationNote.value.trim() || undefined,
      )
      if (operation !== operationSequence || !mounted) return
      candidates.value = candidates.value.map((candidate) => (
        candidate.id === result.id ? result : candidate
      ))
      if (activeTask.value) {
        activeTask.value.candidates = candidates.value
        activeTask.value.journal_id = result.id
      }
    }
    showSaveSuccess()
  } catch (error) {
    const status = (error as { response?: { status?: number } }).response?.status
    if (status === 409) {
      candidates.value = []
      selectedCandidateKey.value = ''
      identified.value = false
      errorMessage.value = '期刊或候选已被修改，请重新识别。'
    } else {
      errorMessage.value = errorText(error, '无法确认期刊身份。')
    }
  } finally {
    confirming.value = false
  }
}

function stageText(stage: string | null | undefined, status: string): string {
  if (status === 'SUCCEEDED') return '识别完成'
  if (status === 'FAILED') return '任务失败'
  if (status === 'CANCELLED') return '任务已取消'
  if (!stage) return '等待 Worker 执行'
  const labels: Record<string, string> = {
    CLAIMED: '任务已领取',
    LOCAL_MATCH: '本地候选查重',
    METADATA_DISCOVERY: '开放数据与网络候选发现',
    OFFICIAL_SITE_VERIFY: '官网身份核验',
    PERSIST: '保存识别结果',
    RETRY_WAIT: '等待重试',
  }
  return labels[stage] ?? stage
}

function statusText(status: DiscoveryCandidate['identity_status']): string {
  const labels = {
    UNVERIFIED: '未验证',
    VERIFIED: '已验证',
    NEEDS_CONFIRMATION: '待确认',
    CONFLICT: '冲突',
    INACTIVE: '不可用',
    UNKNOWN: '未知',
  } as const
  return labels[status]
}

function accessText(status: string | undefined): string {
  const labels: Record<string, string> = {
    PUBLIC_ACCESS: '公开访问',
    LOGIN_REQUIRED: '需要登录',
    ACCESS_RESTRICTED: '访问受限',
    BLOCKED: '访问受阻',
    UNKNOWN: '未知',
  }
  return labels[status ?? 'UNKNOWN'] ?? status ?? '未知'
}
</script>

<template>
  <section aria-labelledby="journal-identification-title">
    <h2 id="journal-identification-title">出版社与期刊识别</h2>
    <form data-test="identify-form" class="stacked-form" novalidate @submit.prevent="identify">
      <div class="form-grid">
        <div style="display: grid; gap: 7px">
          <label for="identify-publisher-name">出版社名称</label>
          <select
            v-if="!publisherCustomMode"
            id="identify-publisher-name"
            v-model="form.publisher_name"
            data-test="identify-publisher-name"
            @change="handlePublisherChange"
          >
            <option value="">请选择出版社</option>
            <option v-for="publisher in publisherOptions" :key="publisher.id" :value="publisher.name">{{ publisher.name }}</option>
            <option :value="CUSTOM_PUBLISHER_VALUE">手动输入新出版社</option>
          </select>
          <template v-else>
            <input id="identify-publisher-name" v-model="form.publisher_name" data-test="identify-publisher-name" maxlength="255" placeholder="请输入新出版社名称">
            <button class="action-button action-button--neutral" type="button" data-test="select-existing-publisher" @click="showExistingPublisherOptions">选择已有出版社</button>
          </template>
        </div>
        <label>期刊名称
          <input v-model="form.journal_name" data-test="identify-journal-name" list="journal-options" maxlength="500" required @input="handleJournalInput">
          <datalist id="journal-options"><option v-for="journal in journalOptions" :key="journal.id" :value="journal.name"></option></datalist>
        </label>
        <label>ISSN<input v-model="form.issn" data-test="identify-issn" placeholder="0378-5955"></label>
        <label>EISSN<input v-model="form.eissn" data-test="identify-eissn" placeholder="1878-1128"></label>
        <label>期刊官网<input v-model="form.website_url" data-test="identify-website" type="url" placeholder="https://journal.example"></label>
        <label>目标文章类型<input v-model="form.article_type" maxlength="100"></label>
      </div>
      <button class="action-button action-button--create" type="submit" :disabled="identifying || isTaskRunning">开始识别</button>
      <button class="action-button action-button--neutral" type="button" data-test="clear-identification" :disabled="identifying || confirming || retrying || cancelling || isTaskRunning" @click="clearIdentification">清空全部</button>
    </form>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="taskStatus">识别任务状态：{{ taskStatus }}</p>
    <section v-if="activeTask" aria-label="网络识别进度">
      <p data-test="task-stage">当前阶段：{{ stageText(activeTask.stage, activeTask.status) }}</p>
      <progress data-test="identification-progress" :value="taskProgress" max="100"></progress><span>{{ taskProgress }}%</span>
      <p v-if="activeTask.message" class="form-error">{{ activeTask.message }}</p>
      <ul v-if="taskWarnings.length" data-test="task-warnings"><li v-for="warning in taskWarnings" :key="warning">{{ warning }}</li></ul>
      <button v-if="isTaskRunning" class="action-button action-button--danger" type="button" data-test="cancel-task" :disabled="cancelling" @click="cancelActiveTask">取消任务</button>
      <button v-if="canRetry" class="action-button action-button--create" type="button" data-test="retry-task" @click="retryActiveTask">{{ ['SUCCEEDED', 'CANCELLED'].includes(taskStatus) ? '重新识别' : '重试任务' }}</button>
    </section>
    <p v-if="identified && isTerminal && candidates.length === 0">未找到候选期刊。</p>

    <section v-if="candidates.length" aria-label="期刊候选">
      <h3>候选期刊</h3>
      <article v-for="candidate in candidates" :key="candidateKey(candidate)" data-test="identity-candidate">
        <label>
          <input v-model="selectedCandidateKey" type="radio" name="journal-candidate" :value="candidateKey(candidate)" :data-test="`select-candidate-${candidateKey(candidate)}`">
          <strong>{{ candidate.name }}</strong>
        </label>
        <dl class="detail-grid">
          <div><dt>出版社</dt><dd>{{ candidate.publisher_name ?? '—' }}</dd></div>
          <div><dt>ISSN</dt><dd>{{ candidate.issn ?? '—' }}</dd></div>
          <div><dt>EISSN</dt><dd>{{ candidate.eissn ?? '—' }}</dd></div>
          <div><dt>官网</dt><dd><a v-if="safeResourceUrl(candidate.website_url)" :href="safeResourceUrl(candidate.website_url) ?? undefined" target="_blank" rel="noopener noreferrer">{{ candidate.website_url }}</a><span v-else>{{ candidate.website_url ?? '—' }}</span></dd></div>
          <div v-if="candidate.author_guidelines_url"><dt>作者指南</dt><dd><a :href="safeResourceUrl(candidate.author_guidelines_url) ?? undefined" target="_blank" rel="noopener noreferrer">{{ candidate.author_guidelines_url }}</a></dd></div>
          <div v-if="candidate.submission_url"><dt>投稿入口</dt><dd><a :href="safeResourceUrl(candidate.submission_url) ?? undefined" target="_blank" rel="noopener noreferrer">{{ candidate.submission_url }}</a>（{{ accessText(candidate.portal_access_status) }}）</dd></div>
          <div v-if="candidate.platform_code"><dt>投稿平台</dt><dd>{{ candidate.platform_code }}</dd></div>
          <div><dt>身份状态</dt><dd>{{ statusText(candidate.identity_status) }}</dd></div>
          <div><dt>匹配原因</dt><dd>{{ candidate.match_reasons?.join('、') || '—' }}</dd></div>
          <div v-if="candidate.sources?.length"><dt>发现来源</dt><dd>{{ candidate.sources.join('、') }}</dd></div>
          <div v-if="candidate.conflict_reason"><dt>冲突原因</dt><dd>{{ candidate.conflict_reason }}</dd></div>
        </dl>
        <details v-if="candidate.evidence?.length" data-test="candidate-evidence">
          <summary>来源证据（{{ candidate.evidence.length }}）</summary>
          <ul><li v-for="evidence in candidate.evidence" :key="`${evidence.source_type}-${evidence.url}`">
            <a :href="safeResourceUrl(evidence.url) ?? undefined" target="_blank" rel="noopener noreferrer">{{ evidence.source_type }}：{{ evidence.title || evidence.url }}</a>
            <span v-if="evidence.http_status">（HTTP {{ evidence.http_status }}）</span>
          </li></ul>
        </details>
      </article>
      <label>确认说明<textarea v-model="confirmationNote" rows="2" maxlength="2000"></textarea></label>
      <button class="action-button action-button--create" type="button" data-test="confirm-identity" :disabled="!canConfirm" @click="confirmSelected">确认所选期刊身份</button>
    </section>
  </section>
</template>
