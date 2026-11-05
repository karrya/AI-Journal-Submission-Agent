<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AuthorResponse } from '../api/authors'
import type {
  ManuscriptAuthor,
  ManuscriptAuthorInput,
  ManuscriptAuthorsUpdate,
} from '../api/manuscripts'

const props = withDefaults(defineProps<{
  modelValue: ManuscriptAuthor[]
  ownerAuthorId: string
  availableAuthors: AuthorResponse[]
  submitting?: boolean
}>(), { submitting: false })

const emit = defineEmits<{
  submit: [payload: ManuscriptAuthorsUpdate]
}>()

const rows = ref<ManuscriptAuthor[]>([])
const selectedAuthorId = ref('')
const confirmed = ref(false)
const error = ref('')

watch(
  () => props.modelValue,
  (value) => {
    confirmed.value = false
    rows.value = value
      .map((author) => ({ ...author }))
      .sort((left, right) => left.position - right.position)
  },
  { immediate: true, deep: true },
)

const remainingAuthors = computed(() => props.availableAuthors.filter(
  (candidate) => !rows.value.some((author) => author.author_id === candidate.id),
))

function addAuthor(): void {
  const author = remainingAuthors.value.find((candidate) => candidate.id === selectedAuthorId.value)
  if (!author) {
    error.value = '请选择要添加的已授权作者。'
    return
  }
  rows.value.push({
    author_id: author.id,
    display_name: author.display_name,
    position: rows.value.length + 1,
    is_corresponding: false,
  })
  selectedAuthorId.value = ''
  confirmed.value = false
  error.value = ''
}

function move(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= rows.value.length) return
  const [entry] = rows.value.splice(index, 1)
  rows.value.splice(target, 0, entry)
  confirmed.value = false
}

function remove(index: number): void {
  if (rows.value[index]?.author_id === props.ownerAuthorId) return
  rows.value.splice(index, 1)
  confirmed.value = false
}

function submit(): void {
  error.value = ''
  if (!confirmed.value) {
    error.value = '保存前请确认作者名单及顺序变更。'
    return
  }
  if (!rows.value.some((author) => author.author_id === props.ownerAuthorId)) {
    error.value = '稿件所有者必须保留在作者名单中。'
    return
  }
  if (!rows.value.some((author) => author.is_corresponding)) {
    error.value = '请至少选择一位通讯作者。'
    return
  }
  const authors: ManuscriptAuthorInput[] = rows.value.map((author, index) => ({
    author_id: author.author_id,
    position: index + 1,
    is_corresponding: author.is_corresponding,
  }))
  emit('submit', { authors, confirm_authorship_change: true })
}
</script>

<template>
  <form class="stacked-form" novalidate @submit.prevent="submit">
    <div class="toolbar">
      <label>添加已授权的共同作者
        <select v-model="selectedAuthorId" data-test="new-author">
          <option value="">请选择作者</option>
          <option v-for="author in remainingAuthors" :key="author.id" :value="author.id">
            {{ author.display_name }}
          </option>
        </select>
      </label>
      <button type="button" data-test="add-author" :disabled="!selectedAuthorId" @click="addAuthor">添加作者</button>
    </div>

    <ol class="authorship-list">
      <li v-for="(author, index) in rows" :key="author.author_id" class="authorship-row">
        <span class="author-position">{{ index + 1 }}</span>
        <span class="author-name">{{ author.display_name }}</span>
        <span v-if="author.author_id === ownerAuthorId">所有者</span>
        <label class="confirmation-control">
          <input
            v-model="author.is_corresponding"
            :data-test="`corresponding-${author.author_id}`"
            type="checkbox"
            @change="confirmed = false"
          >
          通讯作者
        </label>
        <button type="button" :data-test="`move-up-${author.author_id}`" :disabled="index === 0" @click="move(index, -1)">上移</button>
        <button type="button" :data-test="`move-down-${author.author_id}`" :disabled="index === rows.length - 1" @click="move(index, 1)">下移</button>
        <button v-if="author.author_id !== ownerAuthorId" type="button" :data-test="`remove-${author.author_id}`" @click="remove(index)">移除</button>
      </li>
    </ol>

    <label class="confirmation-control">
      <input v-model="confirmed" data-test="authorship-confirm" type="checkbox">
      我确认此作者名单、排列顺序及通讯作者选择。
    </label>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="submitting">保存作者名单</button>
  </form>
</template>
