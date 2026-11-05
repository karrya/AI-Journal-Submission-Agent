<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createJournal,
  createPlatform,
  createPublisher,
  deleteJournal,
  deletePlatform,
  deletePublisher,
  listAllPlatforms,
  listAllPublishers,
  listJournals,
  listPlatforms,
  listPublishers,
  updateJournal,
  updatePlatform,
  updatePublisher,
  type JournalListQuery,
  type JournalPlatformResponse,
  type JournalResponse,
  type PlatformListQuery,
  type PublisherListQuery,
  type PublisherResponse,
} from '../../api/journals'
import type { SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { safeResourceUrl } from '../../utils/url'
import {
  displayText,
  PLATFORM_STATUS_LABELS,
  RESOURCE_KIND_LABELS,
} from '../../utils/display'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const activeTab = ref<'publishers' | 'platforms' | 'journals'>('publishers')
const errorMessage = ref('')
const busy = ref(false)

const publishers = ref<PublisherResponse[]>([])
const publisherTotal = ref(0)
const publisherLoading = ref(false)
const publisherQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'name' as NonNullable<PublisherListQuery['sort']>, order: 'asc' as SortOrder })
const showPublisherForm = ref(false)
const editingPublisherId = ref<string | null>(null)
const publisherForm = reactive({ name: '', website_url: '', notes: '' })
let publisherSequence = 0

const platforms = ref<JournalPlatformResponse[]>([])
const platformTotal = ref(0)
const platformLoading = ref(false)
const platformQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'code' as NonNullable<PlatformListQuery['sort']>, order: 'asc' as SortOrder })
const showPlatformForm = ref(false)
const editingPlatformId = ref<string | null>(null)
const platformForm = reactive({ code: '', name: '', description: '', status: 'active' as 'active' | 'needs_review' | 'disabled' })
let platformSequence = 0

const journals = ref<JournalResponse[]>([])
const journalTotal = ref(0)
const journalLoading = ref(false)
const journalQuery = reactive({ page: 1, page_size: 20, name: '', sort: 'name' as NonNullable<JournalListQuery['sort']>, order: 'asc' as SortOrder })
const showJournalForm = ref(false)
const editingJournalId = ref<string | null>(null)
const publisherOptions = ref<Array<{ id: string; name?: string }>>([])
const platformOptions = ref<Array<{ id: string; name?: string; code?: string }>>([])
const journalForm = reactive({
  publisher_id: '',
  platform_id: '',
  name: '',
  issn: '',
  eissn: '',
  website_url: '',
  submission_url: '',
  author_guidelines_url: '',
  subject_categories: '',
  article_types: '',
  requirements: [] as Array<{ key: string; value: string; value_type: 'string' | 'number' | 'boolean'; scope: string; source_url: string; verified_at: string }>,
  requirements_source_url: '',
  requirements_verified_at: '',
  status: 'active',
  notes: '',
})
let journalSequence = 0

const deleteTarget = ref<{ kind: 'publisher' | 'platform' | 'journal'; id: string } | null>(null)
const deleteConfirmed = ref(false)

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

async function loadPublishers(): Promise<void> {
  const sequence = ++publisherSequence
  publisherLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listPublishers({ ...publisherQuery, name: publisherQuery.name.trim() || undefined })
    if (sequence !== publisherSequence) return
    publishers.value = result.items
    publisherTotal.value = result.total
  } catch (error) {
    if (sequence !== publisherSequence) return
    publishers.value = []
    publisherTotal.value = 0
    errorMessage.value = safeError(error, '无法加载出版商。')
  } finally {
    if (sequence === publisherSequence) publisherLoading.value = false
  }
}

function publisherPage(page: number): void {
  if (publisherLoading.value || page < 1 || (page - 1) * publisherQuery.page_size >= publisherTotal.value) return
  publisherQuery.page = page
  void loadPublishers()
}

function publisherSortChanged(): void {
  publisherQuery.page = 1
  void loadPublishers()
}

function openPublisherForm(publisher?: PublisherResponse): void {
  editingPublisherId.value = publisher?.id ?? null
  Object.assign(publisherForm, { name: publisher?.name ?? '', website_url: publisher?.website_url ?? '', notes: publisher?.notes ?? '' })
  showPublisherForm.value = true
  errorMessage.value = ''
}

async function savePublisher(): Promise<void> {
  if (busy.value) return
  if (!publisherForm.name.trim()) {
    errorMessage.value = '请填写出版商名称。'
    return
  }
  const websiteUrl = nullable(publisherForm.website_url)
  if (websiteUrl && !safeResourceUrl(websiteUrl)) {
    errorMessage.value = '网站地址必须使用 HTTPS，或经允许的本地 HTTP，且不得包含用户信息。'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const payload = { name: publisherForm.name.trim(), website_url: websiteUrl, notes: nullable(publisherForm.notes) }
  try {
    if (editingPublisherId.value) await updatePublisher(editingPublisherId.value, payload)
    else await createPublisher(payload)
    showPublisherForm.value = false
    editingPublisherId.value = null
    await loadPublishers()
  } catch (error) {
    errorMessage.value = safeError(error, '无法保存出版商。')
  } finally {
    busy.value = false
  }
}

async function loadPlatforms(): Promise<void> {
  const sequence = ++platformSequence
  platformLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listPlatforms({ ...platformQuery, name: platformQuery.name.trim() || undefined })
    if (sequence !== platformSequence) return
    platforms.value = result.items
    platformTotal.value = result.total
  } catch (error) {
    if (sequence !== platformSequence) return
    platforms.value = []
    platformTotal.value = 0
    errorMessage.value = safeError(error, '无法加载平台。')
  } finally {
    if (sequence === platformSequence) platformLoading.value = false
  }
}

function platformPage(page: number): void {
  if (platformLoading.value || page < 1 || (page - 1) * platformQuery.page_size >= platformTotal.value) return
  platformQuery.page = page
  void loadPlatforms()
}

function platformSortChanged(): void {
  platformQuery.page = 1
  void loadPlatforms()
}

function openPlatformForm(platform?: JournalPlatformResponse): void {
  editingPlatformId.value = platform?.id ?? null
  Object.assign(platformForm, {
    code: platform?.code ?? '', name: platform?.name ?? '', description: platform?.description ?? '', status: platform?.status ?? 'active',
  })
  showPlatformForm.value = true
  errorMessage.value = ''
}

async function savePlatform(): Promise<void> {
  if (busy.value) return
  if (!platformForm.code.trim() || !platformForm.name.trim()) {
    errorMessage.value = '请填写平台代码和名称。'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const payload = {
    code: platformForm.code.trim(), name: platformForm.name.trim(),
    description: platformForm.description, status: platformForm.status,
  }
  try {
    if (editingPlatformId.value) await updatePlatform(editingPlatformId.value, payload)
    else await createPlatform(payload)
    showPlatformForm.value = false
    editingPlatformId.value = null
    await loadPlatforms()
  } catch (error) {
    errorMessage.value = safeError(error, '无法保存平台。')
  } finally {
    busy.value = false
  }
}

async function loadJournals(): Promise<void> {
  const sequence = ++journalSequence
  journalLoading.value = true
  errorMessage.value = ''
  try {
    const result = await listJournals({ ...journalQuery, name: journalQuery.name.trim() || undefined })
    if (sequence !== journalSequence) return
    journals.value = result.items
    journalTotal.value = result.total
  } catch (error) {
    if (sequence !== journalSequence) return
    journals.value = []
    journalTotal.value = 0
    errorMessage.value = safeError(error, '无法加载期刊。')
  } finally {
    if (sequence === journalSequence) journalLoading.value = false
  }
}

function journalPage(page: number): void {
  if (journalLoading.value || page < 1 || (page - 1) * journalQuery.page_size >= journalTotal.value) return
  journalQuery.page = page
  void loadJournals()
}

function journalSortChanged(): void {
  journalQuery.page = 1
  void loadJournals()
}

function toInputDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

async function openJournalForm(journal?: JournalResponse): Promise<void> {
  editingJournalId.value = journal?.id ?? null
  Object.assign(journalForm, {
    publisher_id: journal?.publisher_id ?? '', platform_id: journal?.platform_id ?? '', name: journal?.name ?? '',
    issn: journal?.issn ?? '', eissn: journal?.eissn ?? '', website_url: journal?.website_url ?? '',
    submission_url: journal?.submission_url ?? '', author_guidelines_url: journal?.author_guidelines_url ?? '',
    subject_categories: journal?.subject_categories.join(', ') ?? '', article_types: journal?.article_types.join(', ') ?? '',
    requirements: journal?.requirements.map((requirement) => ({
      key: requirement.key, value: String(requirement.value),
      value_type: typeof requirement.value === 'number' ? 'number' : typeof requirement.value === 'boolean' ? 'boolean' : 'string',
      scope: requirement.scope,
      source_url: requirement.source_url, verified_at: toInputDate(requirement.verified_at),
    })) ?? [],
    requirements_source_url: journal?.requirements_source_url ?? '',
    requirements_verified_at: journal?.requirements_verified_at ? toInputDate(journal.requirements_verified_at) : '',
    status: journal?.status ?? 'active', notes: journal?.notes ?? '',
  })
  showJournalForm.value = true
  errorMessage.value = ''
  try {
    const [publisherItems, platformItems] = await Promise.all([
      listAllPublishers(),
      listAllPlatforms(),
    ])
    const publisherChoices: Array<{ id: string; name?: string }> = [...publisherItems]
    const platformChoices: Array<{ id: string; name?: string; code?: string }> = [...platformItems]
    if (journal && !publisherChoices.some((option) => option.id === journal.publisher_id)) {
      publisherChoices.unshift({ id: journal.publisher_id })
    }
    if (journal?.platform_id && !platformChoices.some((option) => option.id === journal.platform_id)) {
      platformChoices.unshift({ id: journal.platform_id })
    }
    publisherOptions.value = publisherChoices
    platformOptions.value = platformChoices
  } catch (error) {
    publisherOptions.value = journal ? [{ id: journal.publisher_id }] : []
    platformOptions.value = journal?.platform_id ? [{ id: journal.platform_id }] : []
    errorMessage.value = safeError(error, '无法加载期刊关联选项。')
  }
}

function addRequirement(): void {
  journalForm.requirements.push({ key: '', value: '', value_type: 'string', scope: '', source_url: '', verified_at: '' })
}

function isHttpsUrl(value: string): boolean {
  const safe = safeResourceUrl(value)
  return safe !== null && new URL(safe).protocol === 'https:'
}

function isoDate(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function commaSeparated(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function requirementValue(requirement: { value: string; value_type: 'string' | 'number' | 'boolean' }): string | number | boolean | null {
  const value = requirement.value.trim()
  if (requirement.value_type === 'number') {
    const numeric = Number(value)
    return value && Number.isFinite(numeric) ? numeric : null
  }
  if (requirement.value_type === 'boolean') {
    if (value === 'true') return true
    if (value === 'false') return false
    return null
  }
  return value
}

async function saveJournal(): Promise<void> {
  if (busy.value) return
  errorMessage.value = ''
  if (!journalForm.publisher_id || !journalForm.name.trim()) {
    errorMessage.value = '请选择出版商并填写期刊名称。'
    return
  }
  for (const value of [
    journalForm.website_url,
    journalForm.submission_url,
    journalForm.author_guidelines_url,
    journalForm.requirements_source_url,
  ]) {
    const url = nullable(value)
    if (url && !safeResourceUrl(url)) {
      errorMessage.value = '期刊网址必须使用 HTTPS，或经允许的本地 HTTP，且不得包含用户信息。'
      return
    }
  }
  for (const requirement of journalForm.requirements) {
    if (!requirement.key.trim() || !requirement.value.trim() || !requirement.scope.trim() || !requirement.source_url.trim() || !requirement.verified_at) {
      errorMessage.value = '每一行均须填写要求键、值、适用范围、HTTPS 来源网址和核验时间。'
      return
    }
    if (requirementValue(requirement) === null) {
      errorMessage.value = '要求值必须与所选类型匹配：有限数值、布尔值（是/否）或文本。'
      return
    }
    if (!isHttpsUrl(requirement.source_url.trim())) {
      errorMessage.value = '每项要求的来源网址必须使用 HTTPS，且不得包含用户信息。'
      return
    }
    if (!isoDate(requirement.verified_at)) {
      errorMessage.value = '每项要求的核验时间必须是有效日期。'
      return
    }
  }
  if (journalForm.requirements_verified_at && !isoDate(journalForm.requirements_verified_at)) {
    errorMessage.value = '整体要求核验时间必须是有效日期。'
    return
  }
  const payload = {
    publisher_id: journalForm.publisher_id,
    platform_id: journalForm.platform_id || null,
    name: journalForm.name.trim(),
    issn: nullable(journalForm.issn), eissn: nullable(journalForm.eissn),
    website_url: nullable(journalForm.website_url), submission_url: nullable(journalForm.submission_url),
    author_guidelines_url: nullable(journalForm.author_guidelines_url),
    subject_categories: commaSeparated(journalForm.subject_categories),
    article_types: commaSeparated(journalForm.article_types),
    requirements: journalForm.requirements.map((requirement) => ({
      key: requirement.key.trim(), value: requirementValue(requirement) as string | number | boolean, scope: requirement.scope.trim(),
      source_url: requirement.source_url.trim(), verified_at: isoDate(requirement.verified_at) as string,
    })),
    requirements_source_url: nullable(journalForm.requirements_source_url),
    requirements_verified_at: journalForm.requirements_verified_at ? isoDate(journalForm.requirements_verified_at) : null,
    status: journalForm.status.trim() || 'active', notes: nullable(journalForm.notes),
  }
  busy.value = true
  try {
    if (editingJournalId.value) await updateJournal(editingJournalId.value, payload)
    else await createJournal(payload)
    showJournalForm.value = false
    editingJournalId.value = null
    await loadJournals()
  } catch (error) {
    errorMessage.value = safeError(error, '无法保存期刊。')
  } finally {
    busy.value = false
  }
}

function requestDelete(kind: 'publisher' | 'platform' | 'journal', id: string): void {
  deleteTarget.value = { kind, id }
  deleteConfirmed.value = false
  errorMessage.value = ''
}

async function confirmDelete(): Promise<void> {
  if (!deleteTarget.value || busy.value) return
  if (!deleteConfirmed.value) {
    errorMessage.value = '继续前请确认软删除。'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const { kind, id } = deleteTarget.value
  try {
    if (kind === 'publisher') {
      await deletePublisher(id)
      await loadPublishers()
    } else if (kind === 'platform') {
      await deletePlatform(id)
      await loadPlatforms()
    } else {
      await deleteJournal(id)
      await loadJournals()
    }
    deleteTarget.value = null
  } catch (error) {
    errorMessage.value = safeError(error, '无法删除该资源。')
  } finally {
    busy.value = false
  }
}

function selectTab(tab: 'publishers' | 'platforms' | 'journals'): void {
  activeTab.value = tab
  deleteTarget.value = null
  errorMessage.value = ''
  if (tab === 'publishers') void loadPublishers()
  else if (tab === 'platforms') void loadPlatforms()
  else void loadJournals()
}

function formatIssn(value: string | null | undefined): string {
  if (!value) return '—'
  return /^[0-9X]{8}$/i.test(value) ? `${value.slice(0, 4)}-${value.slice(4)}` : value
}

function formatRequirementValue(value: string | number | boolean): string {
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

onMounted(() => void loadPublishers())
</script>

<template>
  <section class="management-page" aria-labelledby="journal-resources-title">
    <h1 id="journal-resources-title">出版商、平台和期刊</h1>
    <div class="tabs" role="tablist" aria-label="期刊资源">
      <button type="button" role="tab" data-test="publishers-tab" :aria-selected="activeTab === 'publishers'" @click="selectTab('publishers')">出版商</button>
      <button type="button" role="tab" data-test="platforms-tab" :aria-selected="activeTab === 'platforms'" @click="selectTab('platforms')">平台</button>
      <button type="button" role="tab" data-test="journals-tab" :aria-selected="activeTab === 'journals'" @click="selectTab('journals')">期刊</button>
    </div>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <section v-if="activeTab === 'publishers'" aria-label="出版商管理">
      <div class="toolbar">
        <label>搜索名称<input v-model="publisherQuery.name" @change="publisherQuery.page = 1; loadPublishers()"></label>
        <label>排序<select v-model="publisherQuery.sort" data-test="publisher-sort" @change="publisherSortChanged"><option value="name">名称</option><option value="created_at">创建时间</option><option value="updated_at">更新时间</option></select></label>
        <label>顺序<select v-model="publisherQuery.order" @change="publisherSortChanged"><option value="asc">升序</option><option value="desc">降序</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-publisher" @click="openPublisherForm()">添加出版商</button>
      </div>
      <form v-if="showPublisherForm" data-test="publisher-form" class="stacked-form" novalidate @submit.prevent="savePublisher">
        <h2>{{ editingPublisherId ? '编辑出版商' : '添加出版商' }}</h2>
        <label>名称<input v-model="publisherForm.name" data-test="publisher-name" required maxlength="255"></label>
        <label>网站<input v-model="publisherForm.website_url" type="url"></label>
        <label>备注<textarea v-model="publisherForm.notes" rows="3"></textarea></label>
        <button type="submit" :disabled="busy">保存出版商</button><button type="button" @click="showPublisherForm = false">取消</button>
      </form>
      <p v-if="publisherLoading">正在加载出版商…</p><p v-else-if="!errorMessage && publishers.length === 0">未找到出版商。</p>
      <table v-else>
        <thead><tr><th>名称</th><th>网站</th><th v-if="isAdmin">操作</th></tr></thead>
        <tbody><tr v-for="publisher in publishers" :key="publisher.id"><td>{{ publisher.name }}</td><td><template v-if="publisher.website_url"><a v-if="safeResourceUrl(publisher.website_url)" :href="safeResourceUrl(publisher.website_url) ?? undefined" target="_blank" rel="noopener noreferrer">网站</a><span v-else>{{ publisher.website_url }}</span></template><span v-else>—</span></td><td v-if="isAdmin"><button type="button" :data-test="`edit-publisher-${publisher.id}`" @click="openPublisherForm(publisher)">编辑</button><button type="button" :data-test="`delete-publisher-${publisher.id}`" @click="requestDelete('publisher', publisher.id)">删除</button></td></tr></tbody>
      </table>
      <nav class="pagination" aria-label="出版商分页"><button type="button" :disabled="publisherQuery.page === 1 || publisherLoading" @click="publisherPage(publisherQuery.page - 1)">上一页</button><span>第 {{ publisherQuery.page }} 页 · 共 {{ publisherTotal }} 条</span><button type="button" data-test="next-publishers" :disabled="publisherQuery.page * publisherQuery.page_size >= publisherTotal || publisherLoading" @click="publisherPage(publisherQuery.page + 1)">下一页</button></nav>
    </section>

    <section v-else-if="activeTab === 'platforms'" aria-label="平台管理">
      <div class="toolbar">
        <label>搜索名称<input v-model="platformQuery.name" @change="platformQuery.page = 1; loadPlatforms()"></label>
        <label>排序<select v-model="platformQuery.sort" data-test="platform-sort" @change="platformSortChanged"><option value="code">代码</option><option value="name">名称</option><option value="created_at">创建时间</option><option value="updated_at">更新时间</option></select></label>
        <label>顺序<select v-model="platformQuery.order" @change="platformSortChanged"><option value="asc">升序</option><option value="desc">降序</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-platform" @click="openPlatformForm()">添加平台</button>
      </div>
      <form v-if="showPlatformForm" data-test="platform-form" class="stacked-form" novalidate @submit.prevent="savePlatform">
        <h2>{{ editingPlatformId ? '编辑平台' : '添加平台' }}</h2>
        <label>代码<input v-model="platformForm.code" data-test="platform-code" required maxlength="64"></label>
        <label>名称<input v-model="platformForm.name" data-test="platform-name" required maxlength="255"></label>
        <label>描述<textarea v-model="platformForm.description" rows="3"></textarea></label>
        <label>状态<select v-model="platformForm.status"><option value="active">启用</option><option value="needs_review">待审核</option><option value="disabled">已停用</option></select></label>
        <button type="submit" :disabled="busy">保存平台</button><button type="button" @click="showPlatformForm = false">取消</button>
      </form>
      <p v-if="platformLoading">正在加载平台…</p><p v-else-if="!errorMessage && platforms.length === 0">未找到平台。</p>
      <table v-else>
        <thead><tr><th>代码</th><th>名称</th><th>状态</th><th v-if="isAdmin">操作</th></tr></thead>
        <tbody><tr v-for="platform in platforms" :key="platform.id"><td>{{ platform.code }}</td><td>{{ platform.name }}</td><td>{{ displayText(PLATFORM_STATUS_LABELS, platform.status) }}</td><td v-if="isAdmin"><button type="button" :data-test="`edit-platform-${platform.id}`" @click="openPlatformForm(platform)">编辑</button><button type="button" :data-test="`delete-platform-${platform.id}`" @click="requestDelete('platform', platform.id)">删除</button></td></tr></tbody>
      </table>
      <nav class="pagination" aria-label="平台分页"><button type="button" :disabled="platformQuery.page === 1 || platformLoading" @click="platformPage(platformQuery.page - 1)">上一页</button><span>第 {{ platformQuery.page }} 页 · 共 {{ platformTotal }} 条</span><button type="button" data-test="next-platforms" :disabled="platformQuery.page * platformQuery.page_size >= platformTotal || platformLoading" @click="platformPage(platformQuery.page + 1)">下一页</button></nav>
    </section>

    <section v-else aria-label="期刊管理">
      <div class="toolbar">
        <label>搜索名称<input v-model="journalQuery.name" @change="journalQuery.page = 1; loadJournals()"></label>
        <label>排序<select v-model="journalQuery.sort" data-test="journal-sort" @change="journalSortChanged"><option value="name">名称</option><option value="created_at">创建时间</option><option value="updated_at">更新时间</option></select></label>
        <label>顺序<select v-model="journalQuery.order" @change="journalSortChanged"><option value="asc">升序</option><option value="desc">降序</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-journal" @click="openJournalForm()">添加期刊</button>
      </div>
      <form v-if="showJournalForm" data-test="journal-form" class="stacked-form" novalidate @submit.prevent="saveJournal">
        <h2>{{ editingJournalId ? '编辑期刊' : '添加期刊' }}</h2>
        <div class="form-grid">
          <label>出版商<select v-model="journalForm.publisher_id" data-test="journal-publisher" required><option value="" disabled>请选择出版商</option><option v-for="option in publisherOptions" :key="option.id" :value="option.id">{{ option.name ?? option.id }}</option></select></label>
          <label>平台<select v-model="journalForm.platform_id" data-test="journal-platform"><option value="">无平台</option><option v-for="option in platformOptions" :key="option.id" :value="option.id">{{ option.name ?? option.id }}<template v-if="option.code"> ({{ option.code }})</template></option></select></label>
          <label>名称<input v-model="journalForm.name" data-test="journal-name" required maxlength="500"></label>
          <label>状态<input v-model="journalForm.status" required maxlength="32"></label>
          <label>ISSN<input v-model="journalForm.issn" placeholder="0378-5955"></label>
          <label>eISSN<input v-model="journalForm.eissn"></label>
          <label>网站<input v-model="journalForm.website_url" type="url"></label>
          <label>投稿网址<input v-model="journalForm.submission_url" type="url"></label>
          <label>作者指南网址<input v-model="journalForm.author_guidelines_url" type="url"></label>
        </div>
        <label>学科类别（以逗号分隔）<input v-model="journalForm.subject_categories"></label>
        <label>文章类型（以逗号分隔）<input v-model="journalForm.article_types"></label>
        <fieldset>
          <legend>期刊要求</legend>
          <p>每一行均须填写要求键、值、适用范围、HTTPS 来源网址和核验时间。</p>
          <div v-for="(requirement, index) in journalForm.requirements" :key="index" class="requirement-row">
            <div class="form-grid">
              <label>要求键<input v-model="requirement.key" data-test="requirement-key" required></label>
              <label>值类型<select v-model="requirement.value_type" data-test="requirement-type"><option value="string">文本</option><option value="number">数值</option><option value="boolean">布尔值</option></select></label>
              <label>值<select v-if="requirement.value_type === 'boolean'" v-model="requirement.value" data-test="requirement-value" required><option value="true">是</option><option value="false">否</option></select><input v-else v-model="requirement.value" data-test="requirement-value" :type="requirement.value_type === 'number' ? 'number' : 'text'" required></label>
              <label>适用范围<input v-model="requirement.scope" data-test="requirement-scope" required></label>
              <label>HTTPS 来源网址<input v-model="requirement.source_url" data-test="requirement-source" type="url" required></label>
              <label>核验时间<input v-model="requirement.verified_at" data-test="requirement-verified" type="datetime-local" required></label>
            </div>
            <button type="button" @click="journalForm.requirements.splice(index, 1)">移除要求</button>
          </div>
          <button type="button" data-test="add-requirement" @click="addRequirement">添加要求</button>
        </fieldset>
        <label>整体要求来源网址<input v-model="journalForm.requirements_source_url" type="url"></label>
        <label>整体要求核验时间<input v-model="journalForm.requirements_verified_at" type="datetime-local"></label>
        <label>备注<textarea v-model="journalForm.notes" rows="3"></textarea></label>
        <button type="submit" :disabled="busy">保存期刊</button><button type="button" @click="showJournalForm = false">取消</button>
      </form>
      <p v-if="journalLoading">正在加载期刊…</p><p v-else-if="!errorMessage && journals.length === 0">未找到期刊。</p>
      <table v-else>
        <thead><tr><th>名称</th><th>ISSN</th><th>eISSN</th><th>出版商 ID</th><th>平台 ID</th><th>状态</th><th>要求</th><th v-if="isAdmin">操作</th></tr></thead>
        <tbody><tr v-for="journal in journals" :key="journal.id">
          <td>{{ journal.name }}</td><td>{{ formatIssn(journal.issn) }}</td><td>{{ formatIssn(journal.eissn) }}</td><td>{{ journal.publisher_id }}</td><td>{{ journal.platform_id ?? '—' }}</td><td>{{ displayText(PLATFORM_STATUS_LABELS, journal.status) }}</td>
          <td><details><summary>{{ journal.requirements.length }} 项要求</summary><ul><li v-for="(requirement, index) in journal.requirements" :key="`${requirement.key}-${index}`">{{ requirement.key }}: {{ formatRequirementValue(requirement.value) }}（{{ requirement.scope }}） · <template v-if="safeResourceUrl(requirement.source_url)"><a :href="safeResourceUrl(requirement.source_url) ?? undefined" target="_blank" rel="noopener noreferrer">来源</a></template><span v-else>{{ requirement.source_url }}</span> · 核验于 {{ requirement.verified_at }}</li></ul></details></td>
          <td v-if="isAdmin"><button type="button" :data-test="`edit-journal-${journal.id}`" @click="openJournalForm(journal)">编辑</button><button type="button" :data-test="`delete-journal-${journal.id}`" @click="requestDelete('journal', journal.id)">删除</button></td>
        </tr></tbody>
      </table>
      <nav class="pagination" aria-label="期刊分页"><button type="button" :disabled="journalQuery.page === 1 || journalLoading" @click="journalPage(journalQuery.page - 1)">上一页</button><span>第 {{ journalQuery.page }} 页 · 共 {{ journalTotal }} 条</span><button type="button" data-test="next-journals" :disabled="journalQuery.page * journalQuery.page_size >= journalTotal || journalLoading" @click="journalPage(journalQuery.page + 1)">下一页</button></nav>
    </section>

    <section v-if="deleteTarget" class="confirmation-panel" aria-label="确认软删除">
      <h2>确认软删除</h2><p>该{{ displayText(RESOURCE_KIND_LABELS, deleteTarget.kind) }}将从在用列表中移除，历史记录仍会保留。</p>
      <label class="confirmation-control"><input v-model="deleteConfirmed" data-test="delete-confirm" type="checkbox"> 我确认本次软删除。</label>
      <button type="button" :data-test="`confirm-delete-${deleteTarget.kind}-${deleteTarget.id}`" :disabled="busy" @click="confirmDelete">确认删除</button><button type="button" @click="deleteTarget = null">取消</button>
    </section>
  </section>
</template>
