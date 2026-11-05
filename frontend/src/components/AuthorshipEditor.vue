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
    error.value = 'Select an authorized author to add.'
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
    error.value = 'Confirm the ordered authorship change before saving.'
    return
  }
  if (!rows.value.some((author) => author.author_id === props.ownerAuthorId)) {
    error.value = 'The manuscript owner must remain in the author list.'
    return
  }
  if (!rows.value.some((author) => author.is_corresponding)) {
    error.value = 'Select at least one corresponding author.'
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
      <label>Add authorized coauthor
        <select v-model="selectedAuthorId" data-test="new-author">
          <option value="">Select an author</option>
          <option v-for="author in remainingAuthors" :key="author.id" :value="author.id">
            {{ author.display_name }}
          </option>
        </select>
      </label>
      <button type="button" data-test="add-author" :disabled="!selectedAuthorId" @click="addAuthor">Add author</button>
    </div>

    <ol class="authorship-list">
      <li v-for="(author, index) in rows" :key="author.author_id" class="authorship-row">
        <span class="author-position">{{ index + 1 }}</span>
        <span class="author-name">{{ author.display_name }}</span>
        <span v-if="author.author_id === ownerAuthorId">Owner</span>
        <label class="confirmation-control">
          <input
            v-model="author.is_corresponding"
            :data-test="`corresponding-${author.author_id}`"
            type="checkbox"
            @change="confirmed = false"
          >
          Corresponding author
        </label>
        <button type="button" :data-test="`move-up-${author.author_id}`" :disabled="index === 0" @click="move(index, -1)">Move up</button>
        <button type="button" :data-test="`move-down-${author.author_id}`" :disabled="index === rows.length - 1" @click="move(index, 1)">Move down</button>
        <button v-if="author.author_id !== ownerAuthorId" type="button" :data-test="`remove-${author.author_id}`" @click="remove(index)">Remove</button>
      </li>
    </ol>

    <label class="confirmation-control">
      <input v-model="confirmed" data-test="authorship-confirm" type="checkbox">
      I confirm this ordered author list and corresponding-author selection.
    </label>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button type="submit" :disabled="submitting">Save authorship</button>
  </form>
</template>
