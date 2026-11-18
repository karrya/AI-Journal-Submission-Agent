<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  confirmIdentity,
  getJournalOptions,
  getPublisherOptions,
  identifyJournal,
  type IdentifyResponse,
  type JournalCandidate,
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
const candidates = ref<JournalCandidate[]>([])
const selectedJournalId = ref('')
const identified = ref(false)
const identifying = ref(false)
const confirming = ref(false)
const errorMessage = ref('')
const taskStatus = ref('')
const confirmationNote = ref('')
const publisherOptions = ref<PublisherOption[]>([])
const journalOptions = ref<JournalOption[]>([])
const selectedPublisherId = ref('')
let publisherTimer: ReturnType<typeof setTimeout> | undefined
let journalTimer: ReturnType<typeof setTimeout> | undefined
let publisherSequence = 0
let journalSequence = 0

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

function handlePublisherInput(): void {
  clearJournalSelection(Boolean(selectedPublisherId.value))
  if (publisherTimer) clearTimeout(publisherTimer)
  const query = form.publisher_name.trim()
  publisherTimer = setTimeout(() => void loadPublisherOptions(query), 250)
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
  if (publisherTimer) clearTimeout(publisherTimer)
  if (journalTimer) clearTimeout(journalTimer)
  publisherTimer = undefined
  journalTimer = undefined
  publisherSequence += 1
  journalSequence += 1
  form.publisher_name = ''
  form.journal_name = ''
  form.issn = ''
  form.eissn = ''
  form.website_url = ''
  form.article_type = ''
  publisherOptions.value = []
  journalOptions.value = []
  selectedPublisherId.value = ''
  candidates.value = []
  selectedJournalId.value = ''
  identified.value = false
  taskStatus.value = ''
  confirmationNote.value = ''
  errorMessage.value = ''
  void loadPublisherOptions('')
}

onMounted(() => void loadPublisherOptions(''))
onUnmounted(() => {
  if (publisherTimer) clearTimeout(publisherTimer)
  if (journalTimer) clearTimeout(journalTimer)
})

const canConfirm = computed(() => Boolean(
  selectedJournalId.value
  && !confirming.value
  && candidates.value.some((candidate) => candidate.id === selectedJournalId.value)
  && candidates.value.every((candidate) => (
    candidate.identity_status === 'UNVERIFIED' || candidate.identity_status === 'NEEDS_CONFIRMATION'
  ))
))

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
  selectedJournalId.value = ''
  candidates.value = []
  taskStatus.value = ''
  try {
    const result: IdentifyResponse = await identifyJournal({
      publisher_name: optional(form.publisher_name),
      journal_name: form.journal_name.trim(),
      issn: optional(form.issn),
      eissn: optional(form.eissn),
      website_url: optional(form.website_url),
      article_type: optional(form.article_type),
    })
    candidates.value = result.candidates
    taskStatus.value = result.status
    identified.value = true
  } catch (error) {
    errorMessage.value = errorText(error, '无法识别期刊。')
  } finally {
    identifying.value = false
  }
}

async function confirmSelected(): Promise<void> {
  if (!canConfirm.value) return
  const selected = candidates.value.find((candidate) => candidate.id === selectedJournalId.value)
  if (!selected) return
  confirming.value = true
  errorMessage.value = ''
  try {
    const result = await confirmIdentity(
      selected.id,
      selected.updated_at,
      confirmationNote.value.trim() || undefined,
    )
    candidates.value = candidates.value.map((candidate) => (
      candidate.id === result.id ? result : candidate
    ))
    showSaveSuccess()
  } catch (error) {
    const status = (error as { response?: { status?: number } }).response?.status
    if (status === 409) {
      candidates.value = []
      selectedJournalId.value = ''
      identified.value = false
      errorMessage.value = '期刊已被修改，请重新识别。'
    } else {
      errorMessage.value = errorText(error, '无法确认期刊身份。')
    }
  } finally {
    confirming.value = false
  }
}

function statusText(status: JournalCandidate['identity_status']): string {
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
</script>

<template>
  <section aria-labelledby="journal-identification-title">
    <h2 id="journal-identification-title">出版社与期刊识别</h2>
    <form data-test="identify-form" class="stacked-form" novalidate @submit.prevent="identify">
      <div class="form-grid">
        <label>出版社名称
          <input v-model="form.publisher_name" data-test="identify-publisher-name" list="publisher-options" maxlength="255" @input="handlePublisherInput">
          <datalist id="publisher-options"><option v-for="publisher in publisherOptions" :key="publisher.id" :value="publisher.name"></option></datalist>
        </label>
        <label>期刊名称
          <input v-model="form.journal_name" data-test="identify-journal-name" list="journal-options" maxlength="500" required @input="handleJournalInput">
          <datalist id="journal-options"><option v-for="journal in journalOptions" :key="journal.id" :value="journal.name"></option></datalist>
        </label>
        <label>ISSN<input v-model="form.issn" data-test="identify-issn" placeholder="0378-5955"></label>
        <label>EISSN<input v-model="form.eissn" data-test="identify-eissn" placeholder="1878-1128"></label>
        <label>期刊官网<input v-model="form.website_url" data-test="identify-website" type="url" placeholder="https://journal.example"></label>
        <label>目标文章类型<input v-model="form.article_type" maxlength="100"></label>
      </div>
      <button class="action-button action-button--create" type="submit" :disabled="identifying">开始识别</button>
      <button class="action-button action-button--neutral" type="button" data-test="clear-identification" :disabled="identifying || confirming" @click="clearIdentification">清空全部</button>
    </form>
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <p v-if="taskStatus">识别任务状态：{{ taskStatus }}</p>
    <p v-if="identified && candidates.length === 0">未找到候选期刊。</p>

    <section v-if="candidates.length" aria-label="期刊候选">
      <h3>候选期刊</h3>
        <article v-for="candidate in candidates" :key="candidate.id" data-test="identity-candidate">
        <label>
          <input v-model="selectedJournalId" type="radio" name="journal-candidate" :value="candidate.id" :data-test="`select-candidate-${candidate.id}`">
          <strong>{{ candidate.name }}</strong>
        </label>
        <dl class="detail-grid">
          <div><dt>出版社</dt><dd>{{ candidate.publisher_name }}</dd></div>
          <div><dt>ISSN</dt><dd>{{ candidate.issn ?? '—' }}</dd></div>
          <div><dt>EISSN</dt><dd>{{ candidate.eissn ?? '—' }}</dd></div>
          <div><dt>官网</dt><dd><a v-if="safeResourceUrl(candidate.website_url)" :href="safeResourceUrl(candidate.website_url) ?? undefined" target="_blank" rel="noopener noreferrer">{{ candidate.website_url }}</a><span v-else>{{ candidate.website_url ?? '—' }}</span></dd></div>
          <div><dt>身份状态</dt><dd>{{ statusText(candidate.identity_status) }}</dd></div>
          <div><dt>匹配原因</dt><dd>{{ candidate.match_reasons.join('、') || '—' }}</dd></div>
          <div v-if="candidate.conflict_reason"><dt>冲突原因</dt><dd>{{ candidate.conflict_reason }}</dd></div>
        </dl>
      </article>
      <label>确认说明<textarea v-model="confirmationNote" rows="2" maxlength="2000"></textarea></label>
      <button class="action-button action-button--create" type="button" data-test="confirm-identity" :disabled="!canConfirm" @click="confirmSelected">确认所选期刊身份</button>
    </section>
  </section>
</template>
