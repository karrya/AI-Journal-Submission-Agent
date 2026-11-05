<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type {
  AuthorInstitutionLinkCreate,
  AuthorInstitutionLinkResponse,
  AuthorInstitutionLinkUpdate,
  InstitutionSummaryResponse,
} from '../api/authors'

const props = withDefaults(defineProps<{
  institutions: InstitutionSummaryResponse[]
  link?: AuthorInstitutionLinkResponse | null
  submitting?: boolean
}>(), {
  link: null,
  submitting: false,
})

const emit = defineEmits<{
  submit: [payload: AuthorInstitutionLinkCreate | AuthorInstitutionLinkUpdate]
  cancel: []
}>()

const form = reactive({
  institution_id: '',
  department: '',
  position_title: '',
  valid_from: '',
  valid_to: '',
  is_current: false,
  display_order: 0,
  confirm: false,
})
const errorMessage = ref('')

watch(() => props.link, (link) => {
  Object.assign(form, {
    institution_id: link?.institution_id ?? '',
    department: link?.department ?? '',
    position_title: link?.position_title ?? '',
    valid_from: link?.valid_from ?? '',
    valid_to: link?.valid_to ?? '',
    is_current: link?.is_current ?? false,
    display_order: link?.display_order ?? 0,
    confirm: false,
  })
  errorMessage.value = ''
}, { immediate: true })

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

function submit(): void {
  errorMessage.value = ''
  if (!form.institution_id) {
    errorMessage.value = '请选择单位。'
    return
  }
  if (form.valid_from && form.valid_to && form.valid_to < form.valid_from) {
    errorMessage.value = '结束日期不得早于开始日期。'
    return
  }
  if (!Number.isInteger(form.display_order) || form.display_order < 0) {
    errorMessage.value = '显示顺序必须是非负整数。'
    return
  }
  if (!form.confirm) {
    errorMessage.value = '保存前请确认本次单位关联变更。'
    return
  }
  emit('submit', {
    institution_id: form.institution_id,
    department: nullable(form.department),
    position_title: nullable(form.position_title),
    valid_from: form.valid_from || null,
    valid_to: form.valid_to || null,
    is_current: form.is_current,
    display_order: form.display_order,
  })
}
</script>

<template>
  <form class="stacked-form" novalidate @submit.prevent="submit">
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <label>单位
      <select v-model="form.institution_id" data-test="institution-select" required>
        <option value="" disabled>请选择单位</option>
        <option v-for="institution in institutions" :key="institution.id" :value="institution.id">
          {{ institution.name }}<template v-if="institution.city"> — {{ institution.city }}</template><template v-if="institution.country_code"> ({{ institution.country_code }})</template>
        </option>
      </select>
    </label>
    <label>院系<input v-model="form.department" data-test="department" maxlength="255"></label>
    <label>职务<input v-model="form.position_title" maxlength="255"></label>
    <div class="form-grid">
      <label>开始日期<input v-model="form.valid_from" data-test="valid-from" type="date"></label>
      <label>结束日期<input v-model="form.valid_to" data-test="valid-to" type="date"></label>
      <label>显示顺序<input v-model.number="form.display_order" type="number" min="0" step="1"></label>
      <label><input v-model="form.is_current" type="checkbox"> 当前单位</label>
    </div>
    <label class="confirmation-control"><input v-model="form.confirm" data-test="affiliation-confirm" type="checkbox"> 我确认本次作者单位关联变更。</label>
    <div class="form-actions"><button type="submit" :disabled="submitting">保存单位关联</button><button type="button" @click="emit('cancel')">取消</button></div>
  </form>
</template>
