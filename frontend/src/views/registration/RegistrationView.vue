<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  getAuthorizationOptions,
  listAuthorizations,
  listEmails,
  type AuthorizationResponse,
  type EmailResponse,
} from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import {
  getSubmissionPortals,
  type JournalOption,
  type SubmissionPortal,
} from '../../api/identification'
import {
  cancelRegistrationTask,
  createRegistrationTask,
  getPublisherAccounts,
  getRegistrationJournals,
  getRegistrationPlatforms,
  getRegistrationPublishers,
  getRegistrationTasks,
  retryRegistrationTask,
  type PublisherAccount,
  type RegistrationPlatform,
  type RegistrationPublisher,
  type RegistrationTask,
} from '../../api/registration'

const TASK_STATUS_LABELS: Record<string, string> = {
  PENDING: '待执行',
  PROCESSING: '正在处理',
  CHECKING_AUTHORIZATION: '正在核验授权',
  OPENING_PAGE: '正在打开页面',
  DETECTING_FORM: '正在识别表单',
  FILLING_FORM: '正在填写表单',
  WAITING_CAPTCHA: '等待验证码',
  READY_TO_SUBMIT: '等待提交确认',
  SUBMITTING: '正在等待提交结果',
  SUBMITTED: '已提交',
  SUBMISSION_UNKNOWN: '提交结果待核查',
  WAITING_EMAIL: '等待验证邮件',
  WAITING_EMAIL_CONFIRM: '等待邮箱确认',
  VERIFYING_EMAIL: '正在核验邮箱',
  REGISTERED: '注册完成',
  NEEDS_MANUAL_REVIEW: '需要复核',
  FAILED: '执行失败',
  CANCELLED: '已取消',
  EXPIRED: '已过期',
}
const ACCOUNT_STATUS_LABELS: Record<string, string> = {
  REGISTERED: '已注册', ACTIVE: '正常', DISABLED: '已停用', EXPIRED: '已过期',
}
const WORKFLOW_STEPS = ['授权核验', '表单准备', '人工确认', '邮箱验证', '完成']
const TERMINAL_STATUSES = new Set(['REGISTERED', 'FAILED', 'CANCELLED', 'EXPIRED'])

const publishers = ref<RegistrationPublisher[]>([])
const platforms = ref<RegistrationPlatform[]>([])
const authors = ref<Array<{ id: string; display_name: string }>>([])
const journals = ref<JournalOption[]>([])
const journalPortals = ref<SubmissionPortal[]>([])
const filterJournals = ref<JournalOption[]>([])
const authorizations = ref<AuthorizationResponse[]>([])
const registrationEmail = ref<EmailResponse | null>(null)
const tasks = ref<RegistrationTask[]>([])
const accounts = ref<PublisherAccount[]>([])
const total = ref(0)

const catalogLoading = ref(false)
const authorDataLoading = ref(false)
const journalsLoading = ref(false)
const platformsLoading = ref(false)
const filterJournalsLoading = ref(false)
const tasksLoading = ref(false)
const accountsLoading = ref(false)
const creating = ref(false)
const busyTaskId = ref<string | null>(null)
const catalogError = ref('')
const authorDataError = ref('')
const taskError = ref('')
const accountError = ref('')
const actionMessage = ref('')

const target = reactive({
  author_id: '', authorization_id: '', publisher_id: '', journal_id: '', platform_adapter_id: '',
})
const filters = reactive({
  page: 1,
  page_size: 20,
  author_id: '',
  publisher_id: '',
  journal_id: '',
  task_status: '',
  created_from: '',
  created_to: '',
})
const selectedTaskId = ref('')
const cancelTargetId = ref<string | null>(null)
const cancelConfirmed = ref(false)
const evidenceTaskId = ref<string | null>(null)
const evidenceCloseButton = ref<HTMLButtonElement | null>(null)
const evidenceDrawer = ref<HTMLElement | null>(null)
let taskLoadSequence = 0
let journalLoadSequence = 0
let filterJournalLoadSequence = 0
let platformLoadSequence = 0
let authorDataSequence = 0
let createAttempt: { signature: string; key: string } | null = null

const selectedTask = computed(() => tasks.value.find((item) => item.id === selectedTaskId.value) ?? null)
const evidenceTask = computed(() => tasks.value.find((item) => item.id === evidenceTaskId.value) ?? null)
const selectedAuthor = computed(() => authors.value.find((item) => item.id === target.author_id) ?? null)
const selectedPublisher = computed(() => publishers.value.find((item) => item.publisher_id === target.publisher_id) ?? null)
const selectedJournal = computed(() => journals.value.find((item) => item.id === target.journal_id) ?? null)
const platformOptions = computed(() => {
  const bound = new Map<string, RegistrationPlatform>()
  for (const platform of platforms.value) {
    const portal = journalPortals.value.find((item) => (
      item.journal_id === target.journal_id
      && item.platform_adapter_id === platform.id
      && item.platform_code === platform.platform_type
      && item.verification_status === 'VERIFIED'
    ))
    if (portal) bound.set(platform.id, platform)
  }
  return [...bound.values()]
})
const selectedPlatform = computed(() => platformOptions.value.find((item) => item.id === target.platform_adapter_id) ?? null)
const selectedPortal = computed(() => journalPortals.value.find((item) => (
  item.journal_id === target.journal_id && item.platform_adapter_id === target.platform_adapter_id
) && item.platform_code === selectedPlatform.value?.platform_type) ?? null)
const selectedAuthorization = computed(() => authorizations.value.find((item) => item.id === target.authorization_id) ?? null)
const canCreate = computed(() => Boolean(
  target.author_id && target.authorization_id && target.publisher_id && target.journal_id && target.platform_adapter_id
  && selectedPublisher.value?.support_status === 'SUPPORTED'
  && selectedPlatform.value?.support_status === 'SUPPORTED'
  && selectedPortal.value?.support_status === 'SUPPORTED'
  && selectedPortal.value?.verification_status === 'VERIFIED'
  && selectedAuthorization.value?.validity_status === 'active'
  && !authorDataLoading.value && !journalsLoading.value && !platformsLoading.value && !creating.value,
))
const manualGroups = computed(() => [
  {
    id: 'captcha', title: '等待验证码', statuses: ['WAITING_CAPTCHA'],
    consequence: '后果：验证码必须由授权人员在受控人工流程中处理；此处仅定位任务，不会提交答案。',
    tasks: tasks.value.filter((item) => item.task_status === 'WAITING_CAPTCHA'),
  },
  {
    id: 'submit', title: '等待提交确认', statuses: ['READY_TO_SUBMIT', 'SUBMISSION_UNKNOWN'],
    consequence: '后果：提交会改变平台账号状态；请先核对只读摘要，本页面不执行外部提交。',
    tasks: tasks.value.filter((item) => ['READY_TO_SUBMIT', 'SUBMISSION_UNKNOWN'].includes(item.task_status)),
  },
  {
    id: 'email', title: '等待邮箱确认', statuses: ['WAITING_EMAIL', 'WAITING_EMAIL_CONFIRM', 'VERIFYING_EMAIL'],
    consequence: '后果：邮箱确认会推进验证阶段；完整验证链接不会在此显示或导出。',
    tasks: tasks.value.filter((item) => ['WAITING_EMAIL', 'WAITING_EMAIL_CONFIRM', 'VERIFYING_EMAIL'].includes(item.task_status)),
  },
  {
    id: 'review', title: '需要复核', statuses: ['NEEDS_MANUAL_REVIEW'],
    consequence: '后果：复核用于确认异常与账号实际状态，避免重复注册；此处仅查看任务。',
    tasks: tasks.value.filter((item) => item.task_status === 'NEEDS_MANUAL_REVIEW'),
  },
])
const timeline = computed(() => {
  if (!selectedTask.value) return []
  const current = selectedTask.value
  const waiting = current.task_status.includes('WAITING') || current.task_status === 'READY_TO_SUBMIT'
  const warning = waiting || ['FAILED', 'SUBMISSION_UNKNOWN', 'NEEDS_MANUAL_REVIEW'].includes(current.task_status)
  return [
    {
      id: 'created', title: '任务创建', time: formatDate(current.created_at), duration: '耗时未提供',
      detail: '任务已创建并进入受控流程。', warning: false, marker: '记录',
    },
    {
      id: 'current', title: taskStatusLabel(current.task_status), time: '当前任务记录', duration: '耗时未提供',
      detail: safeStep(current.current_step), warning, marker: warning ? '注意' : '当前',
    },
  ]
})

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status
}

function accountStatusLabel(status: string): string {
  return ACCOUNT_STATUS_LABELS[status] ?? status
}

function statusTone(status: string): string {
  if (status === 'REGISTERED') return 'success'
  if (['FAILED', 'EXPIRED'].includes(status)) return 'danger'
  if (status.includes('WAITING') || ['READY_TO_SUBMIT', 'NEEDS_MANUAL_REVIEW', 'SUBMISSION_UNKNOWN'].includes(status)) return 'warning'
  if (status === 'CANCELLED') return 'neutral'
  return 'active'
}

function safeStep(step: string | null): string {
  if (!step) return '当前步骤未提供'
  return step.replace(/https?:\/\/\S+/gi, '[链接已隐藏]')
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function isoDate(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

function maskEmail(value: string): string {
  const [local, domain, ...rest] = value.split('@')
  if (!local || !domain || rest.length > 0) return '已脱敏'
  return `${local.slice(0, 1)}•••@${domain}`
}

function idempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return `registration-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function loadCatalogs(): Promise<void> {
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const [publisherItems, platformItems, options] = await Promise.all([
      getRegistrationPublishers(), getRegistrationPlatforms(), getAuthorizationOptions(),
    ])
    publishers.value = publisherItems
    platforms.value = platformItems
    authors.value = options.authors
  } catch (error) {
    catalogError.value = safeError(error, '无法加载注册目标选项，请稍后重试。')
  } finally {
    catalogLoading.value = false
  }
}

async function onAuthorChange(): Promise<void> {
  const sequence = ++authorDataSequence
  target.authorization_id = ''
  authorizations.value = []
  registrationEmail.value = null
  authorDataError.value = ''
  if (!target.author_id) return
  authorDataLoading.value = true
  try {
    const [authorizationPage, emailPage] = await Promise.all([
      listAuthorizations({ author_id: target.author_id, validity_status: 'active', page_size: 100 }),
      listEmails(target.author_id),
    ])
    if (sequence !== authorDataSequence) return
    authorizations.value = authorizationPage.items
    registrationEmail.value = emailPage.items.find((item) => (
      item.purpose === 'registration' && item.authorization_status === 'authorized'
    )) ?? null
    if (authorizationPage.items.length === 1) target.authorization_id = authorizationPage.items[0].id
  } catch (error) {
    if (sequence === authorDataSequence) {
      authorDataError.value = safeError(error, '无法加载作者授权与注册邮箱。')
    }
  } finally {
    if (sequence === authorDataSequence) authorDataLoading.value = false
  }
}

async function onPublisherChange(): Promise<void> {
  const sequence = ++journalLoadSequence
  platformLoadSequence += 1
  target.journal_id = ''
  target.platform_adapter_id = ''
  journals.value = []
  journalPortals.value = []
  platformsLoading.value = false
  authorDataError.value = ''
  if (!target.publisher_id || selectedPublisher.value?.support_status !== 'SUPPORTED') {
    journalsLoading.value = false
    return
  }
  journalsLoading.value = true
  try {
    const items = await getRegistrationJournals(target.publisher_id)
    if (sequence === journalLoadSequence) journals.value = items
  } catch (error) {
    if (sequence === journalLoadSequence) {
      authorDataError.value = safeError(error, '无法加载该出版社的期刊。')
    }
  } finally {
    if (sequence === journalLoadSequence) journalsLoading.value = false
  }
}

async function onJournalChange(): Promise<void> {
  const sequence = ++platformLoadSequence
  target.platform_adapter_id = ''
  journalPortals.value = []
  authorDataError.value = ''
  if (!target.journal_id) {
    platformsLoading.value = false
    return
  }
  platformsLoading.value = true
  try {
    const items = await getSubmissionPortals(target.journal_id)
    if (sequence === platformLoadSequence) journalPortals.value = items
  } catch (error) {
    if (sequence === platformLoadSequence) {
      authorDataError.value = safeError(error, '无法加载该期刊已绑定的投稿平台。')
    }
  } finally {
    if (sequence === platformLoadSequence) platformsLoading.value = false
  }
}

async function onFilterPublisherChange(): Promise<void> {
  const sequence = ++filterJournalLoadSequence
  filters.journal_id = ''
  filterJournals.value = []
  if (!filters.publisher_id) {
    filterJournalsLoading.value = false
    return
  }
  filterJournalsLoading.value = true
  try {
    const items = await getRegistrationJournals(filters.publisher_id)
    if (sequence === filterJournalLoadSequence) filterJournals.value = items
  } catch (error) {
    if (sequence === filterJournalLoadSequence) {
      taskError.value = safeError(error, '无法加载筛选期刊，现有任务已保留。')
    }
  } finally {
    if (sequence === filterJournalLoadSequence) filterJournalsLoading.value = false
  }
}

async function loadTasks(): Promise<void> {
  const sequence = ++taskLoadSequence
  tasksLoading.value = true
  taskError.value = ''
  try {
    const result = await getRegistrationTasks({
      page: filters.page,
      page_size: filters.page_size,
      author_id: filters.author_id || undefined,
      publisher_id: filters.publisher_id || undefined,
      journal_id: filters.journal_id || undefined,
      task_status: filters.task_status || undefined,
      created_from: isoDate(filters.created_from),
      created_to: isoDate(filters.created_to),
    })
    if (sequence !== taskLoadSequence) return
    tasks.value = result.items
    total.value = result.total
    if (!result.items.some((item) => item.id === selectedTaskId.value)) {
      selectedTaskId.value = result.items[0]?.id ?? ''
    }
    if (!result.items.some((item) => item.id === evidenceTaskId.value)) evidenceTaskId.value = null
    if (!result.items.some((item) => item.id === cancelTargetId.value)) cancelTargetId.value = null
  } catch (error) {
    if (sequence === taskLoadSequence) {
      taskError.value = safeError(error, '无法加载注册任务，当前数据已保留。')
    }
  } finally {
    if (sequence === taskLoadSequence) tasksLoading.value = false
  }
}

function applyFilters(): void {
  if ((filters.created_from && !isoDate(filters.created_from)) || (filters.created_to && !isoDate(filters.created_to))) {
    taskError.value = '筛选时间无效，请检查后重试。'
    return
  }
  filters.page = 1
  void loadTasks()
}

function clearFilters(): void {
  Object.assign(filters, {
    page: 1, author_id: '', publisher_id: '', journal_id: '', task_status: '', created_from: '', created_to: '',
  })
  filterJournals.value = []
  void loadTasks()
}

function changePage(page: number): void {
  if (tasksLoading.value || page < 1 || (page - 1) * filters.page_size >= total.value) return
  filters.page = page
  void loadTasks()
}

async function loadAccounts(): Promise<void> {
  accountsLoading.value = true
  accountError.value = ''
  try {
    accounts.value = (await getPublisherAccounts()).items
  } catch (error) {
    accountError.value = safeError(error, '无法加载出版社账号，当前数据已保留。')
  } finally {
    accountsLoading.value = false
  }
}

async function submitRegistrationTask(): Promise<void> {
  if (!canCreate.value) return
  creating.value = true
  actionMessage.value = ''
  taskError.value = ''
  try {
    const confirmedPayload = {
      author_id: target.author_id,
      publisher_id: target.publisher_id,
      journal_id: target.journal_id,
      authorization_id: target.authorization_id,
      platform_code: selectedPlatform.value!.platform_type,
    }
    const signature = JSON.stringify(confirmedPayload)
    if (!createAttempt || createAttempt.signature !== signature) {
      createAttempt = { signature, key: idempotencyKey() }
    }
    const created = await createRegistrationTask({
      ...confirmedPayload,
      idempotency_key: createAttempt.key,
    })
    createAttempt = null
    tasks.value = [created, ...tasks.value.filter((item) => item.id !== created.id)]
    total.value += 1
    selectedTaskId.value = created.id
    actionMessage.value = `注册任务 ${created.id} 已创建；工作器仅复核授权与入口并转人工复核，不执行外部注册。`
  } catch (error) {
    taskError.value = safeError(error, '无法创建注册任务，请核对授权与支持状态后重试。')
  } finally {
    creating.value = false
  }
}

function selectTask(taskId: string): void {
  selectedTaskId.value = taskId
  cancelTargetId.value = null
  cancelConfirmed.value = false
}

function canCancel(item: RegistrationTask): boolean {
  return !TERMINAL_STATUSES.has(item.task_status)
}

function canRetry(item: RegistrationTask): boolean {
  return item.task_status === 'CANCELLED' || (item.task_status === 'FAILED' && item.retryable)
}

function startCancel(taskId: string): void {
  selectTask(taskId)
  cancelTargetId.value = taskId
  cancelConfirmed.value = false
  actionMessage.value = ''
}

function replaceTask(updated: RegistrationTask): void {
  tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
  selectedTaskId.value = updated.id
}

async function confirmCancel(): Promise<void> {
  if (!cancelTargetId.value || !cancelConfirmed.value || busyTaskId.value) return
  const taskId = cancelTargetId.value
  busyTaskId.value = taskId
  taskError.value = ''
  try {
    replaceTask(await cancelRegistrationTask(taskId))
    cancelTargetId.value = null
    cancelConfirmed.value = false
    actionMessage.value = '任务已取消，不会继续执行后续自动步骤。'
  } catch (error) {
    taskError.value = safeError(error, '无法取消任务，当前状态已保留。')
  } finally {
    busyTaskId.value = null
  }
}

async function retryTask(item: RegistrationTask): Promise<void> {
  if (!canRetry(item) || busyTaskId.value) return
  busyTaskId.value = item.id
  taskError.value = ''
  actionMessage.value = ''
  try {
    replaceTask(await retryRegistrationTask(item.id))
    actionMessage.value = '任务已转入待执行状态；阶段一只重新核验授权和入口准入，不执行外部动作。'
  } catch (error) {
    taskError.value = safeError(error, '无法重试任务，当前状态已保留。')
  } finally {
    busyTaskId.value = null
  }
}

async function openEvidence(taskId: string): Promise<void> {
  evidenceTaskId.value = taskId
  await nextTick()
  evidenceCloseButton.value?.focus()
}

async function closeEvidence(): Promise<void> {
  const taskId = evidenceTaskId.value
  evidenceTaskId.value = null
  await nextTick()
  if (taskId) {
    document.querySelector<HTMLElement>(`[data-test="open-evidence-${taskId}"]`)?.focus()
  }
}

function trapEvidenceFocus(event: KeyboardEvent): void {
  if (event.key !== 'Tab' || !evidenceDrawer.value) return
  const drawer = evidenceDrawer.value
  const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ))
  if (focusable.length === 0) {
    event.preventDefault()
    drawer.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  if (event.shiftKey && (active === first || !drawer.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !drawer.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

function workflowStepState(index: number): { className: string; label: string; marker: string } {
  const item = selectedTask.value
  if (!item) return { className: 'pending', label: '待选择任务', marker: '○' }
  if (item.task_status === 'REGISTERED') return { className: 'complete', label: '已完成', marker: '✓' }
  if (['FAILED', 'CANCELLED', 'EXPIRED'].includes(item.task_status)) {
    return { className: 'unknown', label: '阶段未知 · 流程终止', marker: '?' }
  }
  let currentIndex = 0
  if (['PROCESSING', 'CHECKING_AUTHORIZATION'].includes(item.task_status)) currentIndex = 0
  else if (['OPENING_PAGE', 'DETECTING_FORM', 'FILLING_FORM'].includes(item.task_status)) currentIndex = 1
  else if (['WAITING_CAPTCHA', 'READY_TO_SUBMIT', 'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNKNOWN', 'NEEDS_MANUAL_REVIEW'].includes(item.task_status)) currentIndex = 2
  else if (['WAITING_EMAIL', 'WAITING_EMAIL_CONFIRM', 'VERIFYING_EMAIL'].includes(item.task_status)) currentIndex = 3
  if (index < currentIndex) return { className: 'complete', label: '已完成', marker: '✓' }
  if (index === currentIndex) return { className: 'current', label: '当前阶段', marker: '●' }
  return { className: 'pending', label: '待处理', marker: '○' }
}

function authorName(authorId: string): string {
  return authors.value.find((item) => item.id === authorId)?.display_name ?? `作者 ${authorId}`
}

function publisherName(publisherId: string): string {
  return publishers.value.find((item) => item.publisher_id === publisherId)?.display_name ?? `出版社 ${publisherId}`
}

function journalName(journalId: string): string {
  return [...journals.value, ...filterJournals.value].find((item) => item.id === journalId)?.name ?? `期刊 ${journalId}`
}

function platformName(platformCode: string): string {
  return platforms.value.find((item) => item.platform_type === platformCode)?.adapter_name ?? platformCode
}

onMounted(() => {
  void loadCatalogs()
  void loadTasks()
  void loadAccounts()
})
</script>

<template>
  <section class="registration-page" aria-labelledby="registration-title">
    <div class="registration-content" data-test="registration-content" :inert="evidenceTask ? true : undefined">
    <header class="registration-header">
      <div>
        <p class="eyebrow">REGISTRATION OPERATIONS</p>
        <h1 id="registration-title">注册任务工作台</h1>
        <p class="page-intro">集中核对授权目标、跟踪任务状态并处理人工介入。仅支持已核验的出版社与平台。</p>
      </div>
      <span class="scope-note">阶段一不执行外部注册、邮箱读取或提交；不展示密码、凭据引用或完整验证链接</span>
    </header>

    <p v-if="catalogError" class="inline-alert" role="alert">
      {{ catalogError }} <button type="button" class="text-button" @click="loadCatalogs">重试选项加载</button>
    </p>

    <section class="workbench-panel target-panel" aria-labelledby="registration-target-title">
      <div class="section-heading">
        <div><p class="section-kicker">01 · 目标任务</p><h2 id="registration-target-title">选择作者、出版社、期刊与平台</h2></div>
        <span v-if="catalogLoading" role="status">正在加载选项…</span>
      </div>
      <div class="target-grid">
        <div class="target-card">
          <span class="target-number">1</span>
          <label for="registration-author">作者</label>
          <select id="registration-author" v-model="target.author_id" data-test="registration-author" :disabled="catalogLoading || authorDataLoading" @change="onAuthorChange">
            <option value="">请选择作者</option>
            <option v-for="author in authors" :key="author.id" :value="author.id">{{ author.display_name }}</option>
          </select>
          <label for="registration-authorization">有效授权</label>
          <select id="registration-authorization" v-model="target.authorization_id" data-test="registration-authorization" :disabled="!target.author_id || authorDataLoading">
            <option value="">请选择有效授权</option>
            <option v-for="grant in authorizations" :key="grant.id" :value="grant.id">有效至 {{ formatDate(grant.valid_to) }}</option>
          </select>
        </div>
        <div class="target-card">
          <span class="target-number">2</span>
          <label for="registration-publisher">出版社</label>
          <select id="registration-publisher" v-model="target.publisher_id" data-test="registration-publisher" :disabled="catalogLoading" @change="onPublisherChange">
            <option value="">请选择出版社</option>
            <option
              v-for="publisher in publishers" :key="publisher.id" :value="publisher.publisher_id"
              :disabled="publisher.support_status !== 'SUPPORTED'"
              :data-test="publisher.support_status !== 'SUPPORTED' ? 'unsupported-target' : undefined"
            >{{ publisher.display_name }} · {{ publisher.support_status === 'SUPPORTED' ? '已支持' : '未验收，不可选' }}</option>
          </select>
          <p>仅开放已验收目标；测试中或停用的出版社不可创建任务。</p>
        </div>
        <div class="target-card">
          <span class="target-number">3</span>
          <label for="registration-journal">期刊</label>
          <select id="registration-journal" v-model="target.journal_id" data-test="registration-journal" :disabled="!target.publisher_id || journalsLoading" @change="onJournalChange">
            <option value="">{{ journalsLoading ? '正在加载期刊…' : '请选择期刊' }}</option>
            <option v-for="journal in journals" :key="journal.id" :value="journal.id">{{ journal.name }}</option>
          </select>
          <p v-if="target.publisher_id && !journalsLoading && journals.length === 0">该出版社暂无可选期刊。</p>
          <p v-else>期刊选项来自当前出版社的注册目录。</p>
        </div>
        <div class="target-card">
          <span class="target-number">4</span>
          <label for="registration-platform">投稿平台</label>
          <select id="registration-platform" v-model="target.platform_adapter_id" data-test="registration-platform" :disabled="catalogLoading || !target.journal_id || platformsLoading">
            <option value="">{{ platformsLoading ? '正在加载已绑定平台…' : '请选择投稿平台' }}</option>
            <option
              v-for="platform in platformOptions" :key="platform.id" :value="platform.id"
              :disabled="platform.support_status !== 'SUPPORTED' || journalPortals.find((portal) => portal.platform_adapter_id === platform.id)?.support_status !== 'SUPPORTED'"
              :data-test="platform.support_status !== 'SUPPORTED' ? 'unsupported-platform' : undefined"
            >{{ platform.adapter_name }} · v{{ platform.adapter_version }} · {{ platform.support_status === 'SUPPORTED' ? '已支持' : '未验收，不可选' }}</option>
          </select>
          <p>仅列出当前期刊已核验入口绑定的具体适配器版本；平台最终准入由服务端复核。</p>
        </div>
      </div>
      <p v-if="authorDataError" class="inline-alert" role="alert">{{ authorDataError }}</p>

      <div class="submission-review">
        <section class="confirmation-summary" data-test="confirmation-summary" aria-label="注册提交前只读确认摘要">
          <div class="section-heading compact"><h3>只读确认摘要</h3><span>创建前逐项核对</span></div>
          <dl>
            <div><dt>作者</dt><dd>{{ selectedAuthor?.display_name ?? '尚未选择' }}</dd></div>
            <div><dt>注册邮箱</dt><dd>{{ registrationEmail ? maskEmail(registrationEmail.email) : '未找到已授权注册邮箱' }}</dd></div>
            <div><dt>出版社 / 期刊</dt><dd>{{ selectedPublisher?.display_name ?? '尚未选择' }} / {{ selectedJournal?.name ?? '尚未选择' }}</dd></div>
            <div><dt>平台</dt><dd>{{ selectedPlatform?.adapter_name ?? '尚未选择' }}</dd></div>
            <div><dt>授权</dt><dd>{{ selectedAuthorization ? `有效至 ${formatDate(selectedAuthorization.valid_to)}` : '尚未选择有效授权' }}</dd></div>
            <div><dt>文件</dt><dd>注册任务不接收或发送稿件文件</dd></div>
          </dl>
        </section>
        <div class="submission-action">
          <p>创建任务仅代表进入受控队列。本页面不会直接执行外部注册或跳过人工确认。</p>
          <button type="button" class="primary-button" data-test="create-registration-task" :disabled="!canCreate" @click="submitRegistrationTask">
            {{ creating ? '正在创建…' : '创建注册任务' }}
          </button>
        </div>
      </div>
    </section>

    <p v-if="actionMessage" class="action-message" role="status">{{ actionMessage }}</p>

    <div class="workspace-grid">
      <section class="workbench-panel task-panel" data-test="registration-task-list" :aria-busy="tasksLoading" aria-labelledby="registration-tasks-title">
        <div class="section-heading">
          <div><p class="section-kicker">02 · 任务队列</p><h2 id="registration-tasks-title">注册任务</h2></div>
          <button type="button" class="secondary-button" data-test="refresh-tasks" :disabled="tasksLoading" @click="loadTasks">刷新</button>
        </div>
        <form class="task-filters" aria-label="注册任务筛选" @submit.prevent="applyFilters">
          <label for="task-author-filter">作者</label>
          <select id="task-author-filter" v-model="filters.author_id" data-test="task-author-filter">
            <option value="">全部作者</option><option v-for="author in authors" :key="author.id" :value="author.id">{{ author.display_name }}</option>
          </select>
          <label for="task-publisher-filter">出版社</label>
          <select id="task-publisher-filter" v-model="filters.publisher_id" data-test="task-publisher-filter" @change="onFilterPublisherChange">
            <option value="">全部出版社</option><option v-for="publisher in publishers" :key="publisher.id" :value="publisher.publisher_id">{{ publisher.display_name }}</option>
          </select>
          <label for="task-journal-filter">期刊</label>
          <select id="task-journal-filter" v-model="filters.journal_id" data-test="task-journal-filter" :disabled="filterJournalsLoading || !filters.publisher_id">
            <option value="">全部期刊</option><option v-for="journal in filterJournals" :key="journal.id" :value="journal.id">{{ journal.name }}</option>
          </select>
          <label for="task-status-filter">状态</label>
          <select id="task-status-filter" v-model="filters.task_status" data-test="task-status-filter">
            <option value="">全部状态</option><option v-for="(label, status) in TASK_STATUS_LABELS" :key="status" :value="status">{{ label }}</option>
          </select>
          <label for="created-from-filter">创建时间从</label>
          <input id="created-from-filter" v-model="filters.created_from" data-test="created-from-filter" type="datetime-local">
          <label for="created-to-filter">至</label>
          <input id="created-to-filter" v-model="filters.created_to" data-test="created-to-filter" type="datetime-local">
          <button type="submit" class="secondary-button" data-test="apply-task-filters" :disabled="tasksLoading">应用筛选</button>
          <button type="button" class="text-button" :disabled="tasksLoading" @click="clearFilters">清除筛选</button>
        </form>

        <p v-if="taskError" class="inline-alert" data-test="task-error" role="alert">
          {{ taskError }} <button type="button" class="text-button" data-test="retry-task-load" @click="loadTasks">安全重试</button>
        </p>
        <div v-if="tasksLoading" class="task-skeleton" data-test="task-skeleton" role="status" aria-label="正在加载注册任务">
          <span /><span /><span /><span class="sr-only">正在加载注册任务…</span>
        </div>
        <div v-if="!tasksLoading && !taskError && tasks.length === 0" class="empty-state" data-test="task-empty">
          <strong>暂无符合条件的注册任务</strong><p>可清除筛选查看其他任务，或在上方选择受支持的目标创建任务。</p>
          <button type="button" class="secondary-button" @click="clearFilters">清除筛选</button>
        </div>
        <div v-if="tasks.length" class="task-list">
          <article v-for="item in tasks" :key="item.id" class="task-row" :class="{ selected: selectedTaskId === item.id }" :data-test="`task-${item.id}`">
            <button type="button" class="task-select" :aria-pressed="selectedTaskId === item.id" @click="selectTask(item.id)">
              <span class="task-id">{{ item.id }}</span>
              <span class="status-badge" :class="`status-${statusTone(item.task_status)}`"><span aria-hidden="true">{{ statusTone(item.task_status) === 'warning' || statusTone(item.task_status) === 'danger' ? '!' : '●' }}</span> {{ taskStatusLabel(item.task_status) }}</span>
            </button>
            <dl class="task-metadata">
              <div><dt>作者</dt><dd>{{ authorName(item.author_id) }}</dd></div>
              <div><dt>出版社 / 期刊</dt><dd>{{ publisherName(item.publisher_id) }} / {{ journalName(item.journal_id) }}</dd></div>
              <div><dt>平台</dt><dd>{{ platformName(item.platform_code) }}</dd></div>
              <div><dt>当前步骤 / 最近活动</dt><dd>{{ safeStep(item.current_step) }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ formatDate(item.created_at) }}</dd></div>
            </dl>
            <div class="task-actions">
              <button type="button" class="text-button" :data-test="`open-evidence-${item.id}`" @click="openEvidence(item.id)">查看证据</button>
              <button v-if="canCancel(item)" type="button" class="danger-text-button" :data-test="`cancel-task-${item.id}`" @click="startCancel(item.id)">取消任务</button>
              <button v-if="canRetry(item)" type="button" class="secondary-button" :data-test="`retry-task-${item.id}`" :disabled="busyTaskId === item.id" @click="retryTask(item)">重新识别 / 重试</button>
            </div>
            <section v-if="cancelTargetId === item.id" class="cancel-confirmation" aria-label="确认取消注册任务">
              <strong>确认取消任务 {{ item.id }}</strong>
              <p>后果：任务将停止后续自动步骤；已产生的平台状态不会被撤销。</p>
              <label for="cancel-confirmation"><input id="cancel-confirmation" v-model="cancelConfirmed" data-test="cancel-confirmation" type="checkbox"> 我已了解后果并确认取消。</label>
              <button type="button" class="danger-button" :data-test="`confirm-cancel-${item.id}`" :disabled="!cancelConfirmed || busyTaskId === item.id" @click="confirmCancel">确认取消</button>
              <button type="button" class="text-button" @click="cancelTargetId = null; cancelConfirmed = false">返回</button>
            </section>
          </article>
        </div>
        <nav v-if="total > filters.page_size" class="pagination" aria-label="注册任务分页">
          <button type="button" class="secondary-button" :disabled="filters.page === 1 || tasksLoading" @click="changePage(filters.page - 1)">上一页</button>
          <span>第 {{ filters.page }} 页 · 共 {{ total }} 条</span>
          <button type="button" class="secondary-button" :disabled="filters.page * filters.page_size >= total || tasksLoading" @click="changePage(filters.page + 1)">下一页</button>
        </nav>
      </section>

      <section class="workbench-panel detail-panel" aria-labelledby="task-detail-title">
        <div class="section-heading"><div><p class="section-kicker">03 · 任务详情</p><h2 id="task-detail-title">执行概览</h2></div></div>
        <div v-if="selectedTask" class="selected-task-summary">
          <div><span>任务</span><strong>{{ selectedTask.id }}</strong></div>
          <div><span>作者</span><strong>{{ authorName(selectedTask.author_id) }}</strong></div>
          <div><span>期刊</span><strong>{{ journalName(selectedTask.journal_id) }}</strong></div>
          <div><span>平台</span><strong>{{ platformName(selectedTask.platform_code) }}</strong></div>
          <div data-test="selected-task-status"><span>当前状态</span><strong>{{ taskStatusLabel(selectedTask.task_status) }}</strong></div>
        </div>
        <p v-else class="muted-empty">选择一项任务查看执行步骤和时间线。</p>
        <ol class="workflow-steps" data-test="registration-workflow" aria-label="注册工作流步骤">
          <li v-for="(step, index) in WORKFLOW_STEPS" :key="step" :class="workflowStepState(index).className" :aria-current="selectedTask && workflowStepState(index).className === 'current' ? 'step' : undefined">
            <span class="step-marker" aria-hidden="true">{{ workflowStepState(index).marker }}</span>
            <strong>{{ step }}</strong><small>{{ workflowStepState(index).label }}</small>
          </li>
        </ol>
        <section v-if="selectedTask" class="timeline-card" aria-labelledby="timeline-title">
          <h3 id="timeline-title">执行时间线</h3>
          <ol>
            <li v-for="event in timeline" :key="event.id" :class="{ warning: event.warning }">
              <span class="timeline-marker" aria-hidden="true">{{ event.warning ? '!' : '•' }}</span>
              <div><div class="timeline-heading"><strong>{{ event.title }}</strong><span>{{ event.time }}</span></div><p>{{ event.detail }}</p><small>{{ event.marker }} · {{ event.duration }}<template v-if="event.warning"> · 需要关注，不仅以颜色标识</template></small></div>
            </li>
          </ol>
          <p class="data-note">详细阶段耗时与审计事件需由后端安全摘要提供，此处不补造记录。</p>
        </section>
      </section>
    </div>

    <section class="workbench-panel manual-panel" aria-labelledby="manual-center-title">
      <div class="section-heading"><div><p class="section-kicker">04 · 人工处理中心</p><h2 id="manual-center-title">需要人工关注的任务</h2></div><span>仅查看与定位，不执行外部操作</span></div>
      <div class="manual-grid">
        <section v-for="group in manualGroups" :key="group.id" class="manual-group" :data-test="`manual-${group.id}`" :aria-label="group.title">
          <h3>{{ group.title }} <span>{{ group.tasks.length }}</span></h3>
          <p>{{ group.consequence }}</p>
          <ul v-if="group.tasks.length">
            <li v-for="item in group.tasks" :key="item.id"><span>{{ item.id }} · {{ authorName(item.author_id) }} · {{ platformName(item.platform_code) }}</span><button type="button" class="text-button" @click="selectTask(item.id)">查看任务</button></li>
          </ul>
          <p v-else class="muted-empty">当前没有此类任务。</p>
        </section>
      </div>
    </section>

    <section class="workbench-panel accounts-panel" aria-labelledby="accounts-title">
      <div class="section-heading"><div><p class="section-kicker">05 · 出版社账号</p><h2 id="accounts-title">账号管理</h2></div><button type="button" class="secondary-button" :disabled="accountsLoading" @click="loadAccounts">刷新账号</button></div>
      <p v-if="accountError" class="inline-alert" role="alert">{{ accountError }} <button type="button" class="text-button" @click="loadAccounts">重试</button></p>
      <p v-if="accountsLoading" role="status">正在加载出版社账号…</p>
      <div v-if="!accountsLoading && !accountError && accounts.length === 0" class="empty-state" data-test="account-empty"><strong>暂无出版社账号</strong><p>完成注册并核验后，账号摘要会显示在这里。</p></div>
      <div v-if="accounts.length" class="account-table-wrap" data-test="publisher-accounts">
        <table>
          <caption>账号邮箱默认脱敏；可按需展开非敏感详情。</caption>
          <thead><tr><th scope="col">账号邮箱</th><th scope="col">出版社 / 期刊</th><th scope="col">平台</th><th scope="col">状态</th><th scope="col">邮箱验证</th><th scope="col">最近检查</th><th scope="col">详情</th></tr></thead>
          <tbody><tr v-for="account in accounts" :key="account.id">
            <td>{{ maskEmail(account.account_email) }}</td><td>{{ publisherName(account.publisher_id) }} / {{ account.journal_id ? journalName(account.journal_id) : '未关联' }}</td><td>{{ platformName(account.platform_code) }}</td><td><span class="status-badge status-neutral">{{ accountStatusLabel(account.account_status) }}</span></td><td>{{ formatDate(account.email_verified_at) }}</td><td>{{ formatDate(account.last_checked_at) }}</td>
            <td><details><summary>查看详情</summary><dl class="account-details"><div><dt>账号域</dt><dd>{{ account.account_namespace }}</dd></div><div><dt>平台账号</dt><dd>{{ account.platform_account_id ?? '—' }}</dd></div><div><dt>注册时间</dt><dd>{{ formatDate(account.registered_at) }}</dd></div></dl></details></td>
          </tr></tbody>
        </table>
      </div>
    </section>
    </div>

    <div v-if="evidenceTask" class="drawer-backdrop">
      <aside ref="evidenceDrawer" class="evidence-drawer" data-test="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title" tabindex="-1" @keydown="trapEvidenceFocus" @keydown.esc="closeEvidence">
        <div class="drawer-heading"><div><p class="section-kicker">来源证据</p><h2 id="evidence-title">任务 {{ evidenceTask.id }}</h2></div><button ref="evidenceCloseButton" type="button" class="drawer-close" aria-label="关闭证据抽屉" @click="closeEvidence">关闭</button></div>
        <p>证据抽屉只展示安全来源摘要，不展示完整验证链接或任何凭据。</p>
        <div class="empty-state"><strong>暂无可展示的来源证据</strong><p>当前注册任务接口未提供安全证据摘要。不会将任务字段拼造为来源或证据。</p></div>
        <dl class="evidence-context"><div><dt>目标平台</dt><dd>{{ platformName(evidenceTask.platform_code) }}</dd></div><div><dt>当前状态</dt><dd>{{ taskStatusLabel(evidenceTask.task_status) }}</dd></div></dl>
        <button type="button" class="secondary-button drawer-bottom-close" @click="closeEvidence">关闭证据抽屉</button>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.registration-page { width: min(100%, 1500px); margin: 0 auto; padding: 34px 38px 56px; color: var(--ink); }
.registration-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.eyebrow, .section-kicker { margin: 0 0 7px; color: #526c96; font-size: 11px; font-weight: 700; letter-spacing: .12em; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 10px; font-size: clamp(26px, 3vw, 36px); line-height: 1.2; }
h2 { margin-bottom: 0; font-size: 20px; }
h3 { font-size: 16px; }
.page-intro { max-width: 720px; margin-bottom: 0; color: var(--ink-secondary); line-height: 1.7; }
.scope-note { padding: 8px 12px; color: #36524a; font-size: 12px; background: #eef7f3; border: 1px solid #cee3da; border-radius: 8px; }
.workbench-panel { margin-bottom: 22px; padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 5px 18px rgb(23 32 58 / 4%); }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.section-heading.compact { align-items: center; margin-bottom: 12px; }
.section-heading > span { color: var(--ink-secondary); font-size: 12px; }
.target-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.target-card { position: relative; display: flex; flex-direction: column; gap: 8px; min-width: 0; padding: 18px; background: var(--surface-soft); border: 1px solid #dfe5ef; border-radius: 9px; }
.target-card label { margin-top: 3px; font-size: 13px; font-weight: 650; }
.target-card p { margin: 2px 0 0; color: var(--ink-secondary); font-size: 12px; line-height: 1.55; }
.target-number { display: grid; place-items: center; width: 25px; height: 25px; color: #274f8f; font-size: 12px; font-weight: 700; background: #e8effb; border-radius: 6px; }
select, input { width: 100%; min-height: 40px; padding: 8px 10px; color: var(--ink); background: #fff; border: 1px solid #bdc8d8; border-radius: 7px; }
select:disabled, input:disabled { color: #59667b; background: #eef1f6; cursor: not-allowed; }
.submission-review { display: grid; grid-template-columns: minmax(0, 2fr) minmax(230px, 1fr); gap: 18px; margin-top: 18px; }
.confirmation-summary { padding: 18px; background: #fbfcfe; border: 1px solid #dce4ef; border-radius: 9px; }
.confirmation-summary dl, .selected-task-summary, .task-metadata, .account-details, .evidence-context { margin: 0; }
.confirmation-summary dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 22px; }
.confirmation-summary dl div, .evidence-context div { min-width: 0; }
dt { color: var(--ink-secondary); font-size: 12px; }
dd { margin: 3px 0 0; overflow-wrap: anywhere; font-size: 13px; font-weight: 600; }
.submission-action { display: flex; flex-direction: column; justify-content: center; gap: 12px; padding: 18px; border-left: 2px solid #9db6df; }
.submission-action p { margin: 0; color: var(--ink-secondary); font-size: 13px; line-height: 1.7; }
button { min-height: 38px; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .58; }
.primary-button, .secondary-button, .danger-button, .drawer-close { padding: 9px 14px; border-radius: 7px; font-weight: 650; }
.primary-button { color: #fff; background: #285fbd; border: 1px solid #285fbd; }
.primary-button:hover:not(:disabled) { background: #204e9e; }
.secondary-button, .drawer-close { color: #28466f; background: #fff; border: 1px solid #b9c6d8; }
.danger-button { color: #fff; background: #a43131; border: 1px solid #a43131; }
.text-button, .danger-text-button { min-height: 36px; padding: 4px 6px; color: #285fbd; background: transparent; border: 0; text-decoration: underline; text-underline-offset: 3px; }
.danger-text-button { color: #9a2f2f; }
.inline-alert { margin: 12px 0; padding: 11px 13px; color: #7e2828; background: #fff5f4; border: 1px solid #ebc7c3; border-radius: 8px; line-height: 1.6; }
.action-message { padding: 12px 14px; color: #245c47; background: #eff8f3; border: 1px solid #c9e3d5; border-radius: 8px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(340px, .85fr); gap: 22px; }
.task-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 12px; padding: 16px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: 9px; }
.task-filters label { align-self: end; font-size: 12px; font-weight: 650; }
.task-filters button { align-self: end; }
.task-skeleton { display: grid; gap: 10px; margin-top: 16px; }
.task-skeleton > span:not(.sr-only) { display: block; height: 54px; background: #e9edf3; border: 1px solid #e0e5ed; border-radius: 7px; }
.empty-state { margin-top: 16px; padding: 22px; text-align: center; background: var(--surface-soft); border: 1px dashed #bdc8d8; border-radius: 8px; }
.empty-state p { margin: 7px 0 12px; color: var(--ink-secondary); }
.task-list { display: grid; gap: 12px; margin-top: 16px; }
.task-row { padding: 15px; border: 1px solid #dce3ed; border-radius: 9px; }
.task-row.selected { border-color: #7295cc; box-shadow: inset 3px 0 #346bb9; }
.task-select { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; min-height: 32px; padding: 0; text-align: left; background: transparent; border: 0; }
.task-id { overflow-wrap: anywhere; font-weight: 700; }
.status-badge { display: inline-flex; align-items: center; gap: 5px; width: fit-content; padding: 4px 8px; border: 1px solid; border-radius: 6px; font-size: 12px; white-space: nowrap; }
.status-success { color: #245c47; background: #eff8f3; border-color: #b9d9c8; }
.status-danger { color: #8b2b2b; background: #fff3f2; border-color: #e4bab6; }
.status-warning { color: #735015; background: #fff8e9; border-color: #e6d19f; }
.status-neutral { color: #4e5b6e; background: #f3f5f8; border-color: #ccd4df; }
.status-active { color: #28558f; background: #eff5fd; border-color: #c1d3eb; }
.task-metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin-top: 12px; }
.task-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; margin-top: 10px; }
.cancel-confirmation { margin-top: 12px; padding: 14px; background: #fff7f6; border: 1px solid #e4bab6; border-radius: 8px; }
.cancel-confirmation p { margin: 7px 0; color: #6f3b3b; }
.cancel-confirmation label { display: flex; align-items: center; gap: 9px; margin: 10px 0; }
.cancel-confirmation input { width: 18px; min-height: 18px; }
.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px; }
.selected-task-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 15px; background: var(--surface-soft); border-radius: 8px; }
.selected-task-summary div { display: grid; gap: 3px; min-width: 0; }
.selected-task-summary span { color: var(--ink-secondary); font-size: 12px; }
.selected-task-summary strong { overflow-wrap: anywhere; font-size: 13px; }
.workflow-steps { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 5px; margin: 22px 0; padding: 0; list-style: none; }
.workflow-steps li { display: flex; flex-direction: column; align-items: center; gap: 5px; min-width: 0; padding: 10px 3px; text-align: center; border-bottom: 2px solid #d7dee8; }
.workflow-steps li.complete { border-color: #52816d; }
.workflow-steps li.current { background: #f0f5fc; border-color: #346bb9; }
.workflow-steps li.unknown { border-bottom-style: dashed; }
.workflow-steps strong { font-size: 12px; }
.workflow-steps small { color: var(--ink-secondary); font-size: 10px; }
.step-marker { font-size: 17px; }
.timeline-card { padding: 17px; border: 1px solid var(--line); border-radius: 9px; }
.timeline-card ol { margin: 0; padding: 0; list-style: none; }
.timeline-card li { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.timeline-card li:last-child { border-bottom: 0; }
.timeline-card li.warning { background: #fffbf2; }
.timeline-marker { display: grid; place-items: center; width: 24px; height: 24px; color: #315d96; background: #edf3fb; border-radius: 50%; font-weight: 700; }
.warning .timeline-marker { color: #735015; background: #f8e9c7; }
.timeline-heading { display: flex; justify-content: space-between; gap: 10px; }
.timeline-heading span, .timeline-card small { color: var(--ink-secondary); font-size: 11px; }
.timeline-card p { margin: 5px 0; color: var(--ink-secondary); font-size: 13px; }
.timeline-card .data-note { margin: 12px 0 0; font-size: 11px; }
.manual-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.manual-group { padding: 16px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: 9px; }
.manual-group h3 { display: flex; justify-content: space-between; margin-bottom: 10px; }
.manual-group h3 span { color: var(--ink-secondary); }
.manual-group > p { color: var(--ink-secondary); font-size: 12px; line-height: 1.6; }
.manual-group ul { margin: 0; padding: 0; list-style: none; }
.manual-group li { padding: 10px 0; border-top: 1px solid var(--line); font-size: 12px; overflow-wrap: anywhere; }
.manual-group li button { display: block; padding-left: 0; }
.account-table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
caption { margin-bottom: 10px; color: var(--ink-secondary); text-align: left; }
th, td { padding: 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
th { color: #40506a; background: var(--surface-soft); }
.account-details { min-width: 180px; padding-top: 8px; }
.account-details div { margin-bottom: 8px; }
.muted-empty { color: var(--ink-secondary); }
.drawer-backdrop { position: fixed; z-index: 100; inset: 0; background: rgb(15 25 43 / 35%); }
.evidence-drawer { position: absolute; inset: 0 0 0 auto; width: min(440px, 100%); padding: 26px; overflow-y: auto; background: #fff; border-left: 1px solid #cbd4e1; box-shadow: -10px 0 28px rgb(20 30 50 / 12%); }
.drawer-heading { display: flex; justify-content: space-between; gap: 16px; }
.evidence-context { display: grid; gap: 14px; margin-top: 20px; }
.drawer-bottom-close { width: 100%; margin-top: 20px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 1180px) {
  .target-grid, .manual-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workspace-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .registration-page { padding: 22px 14px 40px; }
  .registration-header, .section-heading { flex-direction: column; gap: 10px; }
  .workbench-panel { padding: 17px; }
  .target-grid, .manual-grid, .submission-review, .confirmation-summary dl, .task-metadata { grid-template-columns: 1fr; }
  .submission-action { border-top: 2px solid #9db6df; border-left: 0; }
  .task-filters { grid-template-columns: 1fr; }
  .workflow-steps { grid-template-columns: 1fr; }
  .workflow-steps li { display: grid; grid-template-columns: 25px 1fr auto; align-items: center; text-align: left; border-bottom: 0; border-left: 2px solid #d7dee8; }
  .workflow-steps li.current { border-left-color: #346bb9; }
  .timeline-heading { flex-direction: column; }
  .primary-button, .secondary-button, .danger-button, .drawer-close, .text-button, .danger-text-button { min-height: 44px; }
  .evidence-drawer { padding: 20px; }
}
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto !important; }
}
</style>
