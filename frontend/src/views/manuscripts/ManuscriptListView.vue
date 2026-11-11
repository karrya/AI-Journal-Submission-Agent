<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listAuthors, type AuthorResponse, type SortOrder } from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import {
  createManuscript,
  listManuscripts,
  type Manuscript,
  type ManuscriptAuthor,
  type ManuscriptAuthorsUpdate,
  type ManuscriptListQuery,
  type ManuscriptStatus,
} from '../../api/manuscripts'
import { fetchAllPages } from '../../api/pagination'
import AuthorshipEditor from '../../components/AuthorshipEditor.vue'
import { useAuthStore } from '../../stores/auth'
import { displayText, MANUSCRIPT_STATUS_LABELS } from '../../utils/display'
import { showSaveSuccess } from '../../utils/feedback'

const auth = useAuthStore()
const canCreate = computed(() => auth.user?.roles.some(
  (role) => role === 'system_admin' || role === 'submission_operator',
) ?? false)

const manuscripts = ref<Manuscript[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const query = reactive({
  page: 1,
  page_size: 20,
  status: '' as ManuscriptStatus | '',
  sort: 'created_at' as NonNullable<ManuscriptListQuery['sort']>,
  order: 'desc' as SortOrder,
})
let loadSequence = 0

const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const authorOptions = ref<AuthorResponse[]>([])
const authorOptionsLoaded = ref(false)
const ownerAuthorId = ref('')
const createAuthors = ref<ManuscriptAuthor[]>([])
const metadata = reactive({
  title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: 'en',
  funding_statement: '', funding_number: '', funding_name: '', publication_statement: '',
  acknowledgements: '', author_contributions: '', clinical_trial_number: '',
  conflict_of_interest_statement: '', ethics_statement: '',
  data_availability_statement: '', notes: '',
})

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await listManuscripts({
      ...query,
      status: query.status || undefined,
    })
    if (sequence !== loadSequence) return
    manuscripts.value = result.items
    total.value = result.total
  } catch (error) {
    if (sequence !== loadSequence) return
    manuscripts.value = []
    total.value = 0
    errorMessage.value = safeError(error, '无法加载稿件。')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function applyFilters(): void {
  query.page = 1
  void load()
}

function changePage(page: number): void {
  if (loading.value || page < 1 || (page - 1) * query.page_size >= total.value) return
  query.page = page
  void load()
}

async function openCreate(): Promise<void> {
  if (!canCreate.value) return
  showCreate.value = true
  createError.value = ''
  if (authorOptionsLoaded.value) return
  try {
    const result = await fetchAllPages((page, pageSize) => listAuthors({
      page, page_size: pageSize, sort: 'display_name', order: 'asc',
    }))
    authorOptions.value = result.items
    authorOptionsLoaded.value = true
  } catch (error) {
    createError.value = safeError(error, '无法加载已授权的所有者选项。')
  }
}

function ownerChanged(): void {
  const owner = authorOptions.value.find((author) => author.id === ownerAuthorId.value)
  createAuthors.value = owner ? [{
    author_id: owner.id,
    display_name: owner.display_name,
    position: 1,
    is_corresponding: true,
  }] : []
}

function nullable(value: string): string | null {
  return value.trim() || null
}

async function saveCreate(authorship: ManuscriptAuthorsUpdate): Promise<void> {
  if (creating.value || !canCreate.value) return
  createError.value = ''
  if (!ownerAuthorId.value || !metadata.title.trim() || !metadata.abstract.trim()
    || !metadata.article_type.trim() || !metadata.language.trim()) {
    createError.value = '请选择所有者，并填写标题、摘要、文章类型和语言。'
    return
  }
  creating.value = true
  try {
    await createManuscript({
      owner_author_id: ownerAuthorId.value,
      title: metadata.title.trim(),
      abstract: metadata.abstract.trim(),
      keywords: metadata.keywords.split(',').map((keyword) => keyword.trim()).filter(Boolean),
      article_type: metadata.article_type.trim(),
      subject_field: nullable(metadata.subject_field),
      language: metadata.language.trim(),
      funding_statement: nullable(metadata.funding_statement),
      funding_number: nullable(metadata.funding_number),
      funding_name: nullable(metadata.funding_name),
      publication_statement: nullable(metadata.publication_statement),
      acknowledgements: nullable(metadata.acknowledgements),
      author_contributions: nullable(metadata.author_contributions),
      clinical_trial_number: nullable(metadata.clinical_trial_number),
      conflict_of_interest_statement: nullable(metadata.conflict_of_interest_statement),
      ethics_statement: nullable(metadata.ethics_statement),
      data_availability_statement: nullable(metadata.data_availability_statement),
      notes: nullable(metadata.notes),
      authors: authorship.authors,
    })
    showCreate.value = false
    ownerAuthorId.value = ''
    createAuthors.value = []
    Object.assign(metadata, {
      title: '', abstract: '', keywords: '', article_type: '', subject_field: '', language: 'en',
      funding_statement: '', funding_number: '', funding_name: '', publication_statement: '',
      acknowledgements: '', author_contributions: '', clinical_trial_number: '',
      conflict_of_interest_statement: '', ethics_statement: '',
      data_availability_statement: '', notes: '',
    })
    await load()
    showSaveSuccess()
  } catch (error) {
    createError.value = safeError(error, '无法创建稿件。')
  } finally {
    creating.value = false
  }
}

function ownerName(manuscript: Manuscript): string {
  return manuscript.authors.find((author) => author.author_id === manuscript.owner_author_id)?.display_name ?? '—'
}

onMounted(() => void load())
</script>

<template>
  <section class="management-page" aria-labelledby="manuscript-list-title">
    <h1 id="manuscript-list-title">稿件</h1>
    <div class="toolbar">
      <label>状态
        <select v-model="query.status" data-test="status-filter">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="active">进行中</option>
          <option value="archived">已归档</option>
        </select>
      </label>
      <label>排序
        <select v-model="query.sort" data-test="manuscript-sort" @change="applyFilters">
          <option value="created_at">创建时间</option>
          <option value="updated_at">更新时间</option>
          <option value="title">标题</option>
        </select>
      </label>
      <label>顺序
        <select v-model="query.order" @change="applyFilters">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </label>
      <button class="action-button action-button--neutral" type="button" data-test="apply-filters" @click="applyFilters">应用筛选</button>
      <button v-if="canCreate" class="action-button action-button--create" type="button" data-test="add-manuscript" @click="openCreate">新建稿件</button>
    </div>

    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <section v-if="showCreate" aria-labelledby="create-manuscript-title">
      <h2 id="create-manuscript-title">创建稿件</h2>
      <div class="stacked-form">
        <label>所有者作者
          <select v-model="ownerAuthorId" data-test="owner-author" required @change="ownerChanged">
            <option value="">请选择已授权的所有者</option>
            <option v-for="author in authorOptions" :key="author.id" :value="author.id">{{ author.display_name }}</option>
          </select>
        </label>
        <div class="form-grid">
          <label>标题<input v-model="metadata.title" data-test="title" maxlength="1000" required></label>
          <label>文章类型<input v-model="metadata.article_type" data-test="article-type" maxlength="100" required></label>
          <label>语言<select v-model="metadata.language" data-test="language" required><option value="en">英语</option><option value="zh">中文</option></select></label>
          <label>学科领域<input v-model="metadata.subject_field" maxlength="255"></label>
          <label>关键词（以逗号分隔）<input v-model="metadata.keywords" data-test="keywords"></label>
          <label>基金编号<input v-model="metadata.funding_number" data-test="funding-number" maxlength="255"></label>
          <label>基金名称<input v-model="metadata.funding_name" data-test="funding-name" maxlength="255"></label>
          <label>临床实验编号（医学）<input v-model="metadata.clinical_trial_number" data-test="clinical-trial-number" maxlength="255"></label>
        </div>
        <label>摘要<textarea v-model="metadata.abstract" data-test="abstract" rows="6" required></textarea></label>
        <label>基金声明<textarea v-model="metadata.funding_statement" rows="3"></textarea></label>
        <label>出版声明<textarea v-model="metadata.publication_statement" data-test="publication-statement" rows="3"></textarea></label>
        <label>致谢<textarea v-model="metadata.acknowledgements" data-test="acknowledgements" rows="3"></textarea></label>
        <label>作者贡献<textarea v-model="metadata.author_contributions" data-test="author-contributions" rows="3"></textarea></label>
        <label>利益冲突声明<textarea v-model="metadata.conflict_of_interest_statement" rows="3"></textarea></label>
        <label>伦理声明<textarea v-model="metadata.ethics_statement" rows="3"></textarea></label>
        <label>数据可用性声明<textarea v-model="metadata.data_availability_statement" rows="3"></textarea></label>
        <label>备注<textarea v-model="metadata.notes" rows="3"></textarea></label>
      </div>
      <AuthorshipEditor
        v-if="ownerAuthorId"
        data-test="create-authorship-form"
        :model-value="createAuthors"
        :owner-author-id="ownerAuthorId"
        :available-authors="authorOptions"
        :submitting="creating"
        @submit="saveCreate"
      />
      <p v-if="createError" class="form-error" role="alert">{{ createError }}</p>
      <button class="action-button action-button--compact action-button--neutral" type="button" :disabled="creating" @click="showCreate = false">取消</button>
    </section>

    <p v-if="loading">正在加载稿件…</p>
    <p v-else-if="!errorMessage && manuscripts.length === 0">未找到稿件。</p>
    <table v-else>
      <thead><tr><th>内部编号</th><th>标题</th><th>所有者</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="manuscript in manuscripts" :key="manuscript.id">
        <td>{{ manuscript.internal_number }}</td>
        <td>{{ manuscript.title }}</td>
        <td>{{ ownerName(manuscript) }}</td>
        <td>{{ displayText(MANUSCRIPT_STATUS_LABELS, manuscript.status) }}</td>
        <td><time :datetime="manuscript.updated_at">{{ manuscript.updated_at }}</time></td>
        <td><RouterLink class="action-button action-button--compact action-button--view" :to="`/manuscripts/${manuscript.id}`">打开工作区</RouterLink></td>
      </tr></tbody>
    </table>
    <nav class="pagination" aria-label="稿件分页">
      <button class="action-button action-button--compact action-button--neutral" type="button" :disabled="query.page === 1 || loading" @click="changePage(query.page - 1)">上一页</button>
      <span>第 {{ query.page }} 页 · 共 {{ total }} 条</span>
      <button class="action-button action-button--compact action-button--neutral" type="button" data-test="next-manuscripts" :disabled="query.page * query.page_size >= total || loading" @click="changePage(query.page + 1)">下一页</button>
    </nav>
  </section>
</template>
