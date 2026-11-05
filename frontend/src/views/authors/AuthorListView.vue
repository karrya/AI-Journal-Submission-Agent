<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  createAuthor,
  createInstitution,
  deleteAuthor,
  deleteInstitution,
  listAuthors,
  listInstitutions,
  updateInstitution,
  type AuthorCreate,
  type AuthorListQuery,
  type AuthorResponse,
  type AuthorUpdate,
  type InstitutionCreate,
  type InstitutionListQuery,
  type InstitutionSummaryResponse,
  type InstitutionUpdate,
  type SortOrder,
} from '../../api/authors'
import { getSafeRequestId } from '../../api/client'
import AuthorForm from '../../components/AuthorForm.vue'
import { useAuthStore } from '../../stores/auth'
import { safeResourceUrl } from '../../utils/url'
import { AUTHOR_STATUS_LABELS, displayText } from '../../utils/display'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.roles.includes('system_admin') ?? false)
const activeTab = ref<'authors' | 'institutions'>('authors')

const authors = ref<AuthorResponse[]>([])
const authorTotal = ref(0)
const authorLoading = ref(false)
const authorError = ref('')
const authorQuery = reactive({
  page: 1,
  page_size: 20,
  name: '',
  sort: 'display_name' as NonNullable<AuthorListQuery['sort']>,
  order: 'asc' as SortOrder,
})
const showAuthorForm = ref(false)
const authorBusy = ref(false)
const deletingAuthorId = ref<string | null>(null)
const authorDeleteConfirmed = ref(false)
let authorSequence = 0

const institutions = ref<InstitutionSummaryResponse[]>([])
const institutionTotal = ref(0)
const institutionLoading = ref(false)
const institutionError = ref('')
const institutionQuery = reactive({
  page: 1,
  page_size: 20,
  name: '',
  sort: 'name' as NonNullable<InstitutionListQuery['sort']>,
  order: 'asc' as SortOrder,
})
const showInstitutionForm = ref(false)
const editingInstitutionId = ref<string | null>(null)
const institutionBusy = ref(false)
const institutionForm = reactive({
  name: '',
  institution_type: '',
  website_url: '',
  country_code: '',
  city: '',
})
const deletingInstitutionId = ref<string | null>(null)
const institutionDeleteConfirmed = ref(false)
let institutionSequence = 0

function safeError(error: unknown, fallback: string): string {
  const requestId = getSafeRequestId(error)
  return requestId ? `${fallback} 请求 ID：${requestId}` : fallback
}

async function loadAuthors(): Promise<void> {
  const sequence = ++authorSequence
  authorLoading.value = true
  authorError.value = ''
  try {
    const page = await listAuthors({
      ...authorQuery,
      name: authorQuery.name.trim() || undefined,
    })
    if (sequence !== authorSequence) return
    authors.value = page.items
    authorTotal.value = page.total
  } catch (error) {
    if (sequence !== authorSequence) return
    authors.value = []
    authorTotal.value = 0
    authorError.value = safeError(error, '无法加载作者。')
  } finally {
    if (sequence === authorSequence) authorLoading.value = false
  }
}

function authorPage(page: number): void {
  if (authorLoading.value || page < 1 || (page - 1) * authorQuery.page_size >= authorTotal.value) return
  authorQuery.page = page
  void loadAuthors()
}

function authorSortChanged(): void {
  authorQuery.page = 1
  void loadAuthors()
}

async function saveAuthor(payload: AuthorCreate | AuthorUpdate): Promise<void> {
  if (authorBusy.value) return
  authorBusy.value = true
  authorError.value = ''
  try {
    await createAuthor(payload as AuthorCreate)
    showAuthorForm.value = false
    await loadAuthors()
  } catch (error) {
    authorError.value = safeError(error, '无法创建作者。')
  } finally {
    authorBusy.value = false
  }
}

function requestAuthorDelete(authorId: string): void {
  deletingAuthorId.value = authorId
  authorDeleteConfirmed.value = false
  authorError.value = ''
}

async function confirmAuthorDelete(): Promise<void> {
  if (!deletingAuthorId.value || authorBusy.value) return
  if (!authorDeleteConfirmed.value) {
    authorError.value = '继续前请确认软删除该作者。'
    return
  }
  authorBusy.value = true
  authorError.value = ''
  try {
    await deleteAuthor(deletingAuthorId.value)
    deletingAuthorId.value = null
    await loadAuthors()
  } catch (error) {
    authorError.value = safeError(error, '无法删除作者。')
  } finally {
    authorBusy.value = false
  }
}

async function loadInstitutions(): Promise<void> {
  const sequence = ++institutionSequence
  institutionLoading.value = true
  institutionError.value = ''
  try {
    const page = await listInstitutions({
      ...institutionQuery,
      name: institutionQuery.name.trim() || undefined,
    })
    if (sequence !== institutionSequence) return
    institutions.value = page.items
    institutionTotal.value = page.total
  } catch (error) {
    if (sequence !== institutionSequence) return
    institutions.value = []
    institutionTotal.value = 0
    institutionError.value = safeError(error, '无法加载单位。')
  } finally {
    if (sequence === institutionSequence) institutionLoading.value = false
  }
}

function institutionPage(page: number): void {
  if (institutionLoading.value || page < 1 || (page - 1) * institutionQuery.page_size >= institutionTotal.value) return
  institutionQuery.page = page
  void loadInstitutions()
}

function institutionSortChanged(): void {
  institutionQuery.page = 1
  void loadInstitutions()
}

function selectTab(tab: 'authors' | 'institutions'): void {
  activeTab.value = tab
  if (tab === 'institutions') void loadInstitutions()
}

function openInstitutionForm(institution?: InstitutionSummaryResponse): void {
  editingInstitutionId.value = institution?.id ?? null
  Object.assign(institutionForm, {
    name: institution?.name ?? '',
    institution_type: institution?.institution_type ?? '',
    website_url: institution?.website_url ?? '',
    country_code: institution?.country_code ?? '',
    city: institution?.city ?? '',
  })
  showInstitutionForm.value = true
  institutionError.value = ''
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

async function saveInstitution(): Promise<void> {
  if (institutionBusy.value) return
  institutionError.value = ''
  if (!institutionForm.name.trim()) {
    institutionError.value = '请填写单位名称。'
    return
  }
  const websiteUrl = nullable(institutionForm.website_url)
  if (websiteUrl && !safeResourceUrl(websiteUrl)) {
    institutionError.value = '网站地址必须使用 HTTPS，或经允许的本地 HTTP，且不得包含用户信息。'
    return
  }
  const fields = {
    institution_type: nullable(institutionForm.institution_type),
    website_url: websiteUrl,
    country_code: nullable(institutionForm.country_code)?.toUpperCase() ?? null,
    city: nullable(institutionForm.city),
  }
  institutionBusy.value = true
  try {
    if (editingInstitutionId.value) {
      const payload: InstitutionUpdate = { name: institutionForm.name.trim(), ...fields }
      await updateInstitution(editingInstitutionId.value, payload)
    } else {
      const payload: InstitutionCreate = { name: institutionForm.name.trim(), ...fields }
      await createInstitution(payload)
    }
    showInstitutionForm.value = false
    editingInstitutionId.value = null
    await loadInstitutions()
  } catch (error) {
    institutionError.value = safeError(error, '无法保存单位。')
  } finally {
    institutionBusy.value = false
  }
}

function requestInstitutionDelete(institutionId: string): void {
  deletingInstitutionId.value = institutionId
  institutionDeleteConfirmed.value = false
  institutionError.value = ''
}

async function confirmInstitutionDelete(): Promise<void> {
  if (!deletingInstitutionId.value || institutionBusy.value) return
  if (!institutionDeleteConfirmed.value) {
    institutionError.value = '继续前请确认软删除该单位。'
    return
  }
  institutionBusy.value = true
  institutionError.value = ''
  try {
    await deleteInstitution(deletingInstitutionId.value)
    deletingInstitutionId.value = null
    await loadInstitutions()
  } catch (error) {
    institutionError.value = safeError(error, '无法删除单位。')
  } finally {
    institutionBusy.value = false
  }
}

onMounted(() => void loadAuthors())
</script>

<template>
  <section class="management-page" aria-labelledby="author-list-title">
    <h1 id="author-list-title">作者和单位</h1>
    <div class="tabs" role="tablist" aria-label="作者资源">
      <button type="button" role="tab" :aria-selected="activeTab === 'authors'" @click="selectTab('authors')">作者</button>
      <button type="button" role="tab" data-test="institutions-tab" :aria-selected="activeTab === 'institutions'" @click="selectTab('institutions')">单位</button>
    </div>

    <section v-if="activeTab === 'authors'" aria-label="作者管理">
      <div class="toolbar">
        <label>搜索姓名<input v-model="authorQuery.name" data-test="author-name-filter" @change="authorQuery.page = 1; loadAuthors()"></label>
        <label>排序<select v-model="authorQuery.sort" data-test="author-sort" @change="authorSortChanged"><option value="display_name">显示姓名</option><option value="created_at">创建时间</option><option value="updated_at">更新时间</option></select></label>
        <label>顺序<select v-model="authorQuery.order" @change="authorSortChanged"><option value="asc">升序</option><option value="desc">降序</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-author" @click="showAuthorForm = true">添加作者</button>
      </div>
      <p v-if="authorError" class="form-error" role="alert">{{ authorError }}</p>
      <AuthorForm v-if="showAuthorForm" data-test="author-create-form" :submitting="authorBusy" @submit="saveAuthor" @cancel="showAuthorForm = false" />
      <p v-if="authorLoading">正在加载作者…</p>
      <p v-else-if="!authorError && authors.length === 0">未找到作者。</p>
      <table v-else>
        <thead><tr><th>显示姓名</th><th>ORCID</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="author in authors" :key="author.id">
          <td>{{ author.display_name }}</td><td>{{ author.orcid ?? '—' }}</td><td>{{ displayText(AUTHOR_STATUS_LABELS, author.status) }}</td>
          <td class="table-actions">
            <RouterLink :to="`/authors/${author.id}`">查看</RouterLink>
            <RouterLink :to="`/authors/${author.id}/authorizations`">授权</RouterLink>
            <button v-if="isAdmin" type="button" :data-test="`delete-author-${author.id}`" @click="requestAuthorDelete(author.id)">删除</button>
          </td>
        </tr></tbody>
      </table>
      <section v-if="deletingAuthorId" class="confirmation-panel" aria-label="确认删除作者">
        <p>确定软删除该作者吗？历史记录将保留，但该资料会从在用列表中移除。</p>
        <label class="confirmation-control"><input v-model="authorDeleteConfirmed" data-test="author-delete-confirm" type="checkbox"> 我确认软删除该作者。</label>
        <button type="button" :data-test="`confirm-delete-author-${deletingAuthorId}`" @click="confirmAuthorDelete">确认删除</button>
        <button type="button" @click="deletingAuthorId = null">取消</button>
      </section>
      <nav class="pagination" aria-label="作者分页">
        <button type="button" :disabled="authorQuery.page === 1 || authorLoading" @click="authorPage(authorQuery.page - 1)">上一页</button>
        <span>第 {{ authorQuery.page }} 页 · 共 {{ authorTotal }} 条</span>
        <button type="button" data-test="next-authors" :disabled="authorQuery.page * authorQuery.page_size >= authorTotal || authorLoading" @click="authorPage(authorQuery.page + 1)">下一页</button>
      </nav>
    </section>

    <section v-else aria-label="单位管理">
      <div class="toolbar">
        <label>搜索名称<input v-model="institutionQuery.name" @change="institutionQuery.page = 1; loadInstitutions()"></label>
        <label>排序<select v-model="institutionQuery.sort" @change="institutionSortChanged"><option value="name">名称</option><option value="created_at">创建时间</option><option value="updated_at">更新时间</option></select></label>
        <label>顺序<select v-model="institutionQuery.order" @change="institutionSortChanged"><option value="asc">升序</option><option value="desc">降序</option></select></label>
        <button v-if="isAdmin" type="button" data-test="add-institution" @click="openInstitutionForm()">添加单位</button>
      </div>
      <p v-if="institutionError" class="form-error" role="alert">{{ institutionError }}</p>
      <form v-if="showInstitutionForm" data-test="institution-form" class="stacked-form" novalidate @submit.prevent="saveInstitution">
        <h2>{{ editingInstitutionId ? '编辑单位' : '添加单位' }}</h2>
        <div class="form-grid">
          <label>名称<input v-model="institutionForm.name" data-test="institution-name" required maxlength="255"></label>
          <label>类型<input v-model="institutionForm.institution_type" maxlength="32"></label>
          <label>网站<input v-model="institutionForm.website_url" data-test="institution-website" type="url"></label>
          <label>国家代码<input v-model="institutionForm.country_code" maxlength="2" placeholder="CN"></label>
          <label>城市<input v-model="institutionForm.city" maxlength="128"></label>
        </div>
        <button type="submit" :disabled="institutionBusy">保存单位</button>
        <button type="button" @click="showInstitutionForm = false">取消</button>
      </form>
      <p v-if="institutionLoading">正在加载单位…</p>
      <p v-else-if="!institutionError && institutions.length === 0">未找到单位。</p>
      <table v-else>
        <thead><tr><th>名称</th><th>类型</th><th>城市</th><th>国家</th><th>网站</th><th v-if="isAdmin">操作</th></tr></thead>
        <tbody><tr v-for="institution in institutions" :key="institution.id">
          <td>{{ institution.name }}</td><td>{{ institution.institution_type ?? '—' }}</td><td>{{ institution.city ?? '—' }}</td><td>{{ institution.country_code ?? '—' }}</td>
          <td><template v-if="institution.website_url"><a v-if="safeResourceUrl(institution.website_url)" :href="safeResourceUrl(institution.website_url) ?? undefined" rel="noopener noreferrer" target="_blank">网站</a><span v-else>{{ institution.website_url }}</span></template><span v-else>—</span></td>
          <td v-if="isAdmin"><button type="button" :data-test="`edit-institution-${institution.id}`" @click="openInstitutionForm(institution)">编辑</button><button type="button" :data-test="`delete-institution-${institution.id}`" @click="requestInstitutionDelete(institution.id)">删除</button></td>
        </tr></tbody>
      </table>
      <section v-if="deletingInstitutionId" class="confirmation-panel" aria-label="确认删除单位">
        <p>确定软删除该单位吗？现有作者关联需另行管理。</p>
        <label class="confirmation-control"><input v-model="institutionDeleteConfirmed" data-test="institution-delete-confirm" type="checkbox"> 我确认软删除该单位。</label>
        <button type="button" :data-test="`confirm-delete-institution-${deletingInstitutionId}`" @click="confirmInstitutionDelete">确认删除</button>
        <button type="button" @click="deletingInstitutionId = null">取消</button>
      </section>
      <nav class="pagination" aria-label="单位分页">
        <button type="button" :disabled="institutionQuery.page === 1 || institutionLoading" @click="institutionPage(institutionQuery.page - 1)">上一页</button>
        <span>第 {{ institutionQuery.page }} 页 · 共 {{ institutionTotal }} 条</span>
        <button type="button" :disabled="institutionQuery.page * institutionQuery.page_size >= institutionTotal || institutionLoading" @click="institutionPage(institutionQuery.page + 1)">下一页</button>
      </nav>
    </section>
  </section>
</template>
