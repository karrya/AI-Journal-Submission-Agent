<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { AuthorCreate, AuthorResponse, AuthorUpdate } from '../api/authors'

const props = withDefaults(defineProps<{
  author?: AuthorResponse | null
  submitting?: boolean
}>(), {
  author: null,
  submitting: false,
})

const emit = defineEmits<{
  submit: [payload: AuthorCreate | AuthorUpdate]
  cancel: []
}>()

interface FormState {
  given_name: string
  middle_name: string
  family_name: string
  display_name: string
  orcid: string
  phone_country_code: string
  phone_number: string
  status: 'active' | 'inactive'
  notes: string
  confirm_identity_change: boolean
}

const emptyForm = (): FormState => ({
  given_name: '',
  middle_name: '',
  family_name: '',
  display_name: '',
  orcid: '',
  phone_country_code: '',
  phone_number: '',
  status: 'active',
  notes: '',
  confirm_identity_change: false,
})

const form = reactive<FormState>(emptyForm())
const errorMessage = ref('')
type OptionalAuthorField =
  | 'given_name'
  | 'middle_name'
  | 'family_name'
  | 'orcid'
  | 'phone_country_code'
  | 'phone_number'
  | 'notes'

function hasResponseField(field: OptionalAuthorField): boolean {
  return props.author !== null && Object.prototype.hasOwnProperty.call(props.author, field)
}

function canEditField(field: OptionalAuthorField): boolean {
  return !props.author || hasResponseField(field)
}

watch(() => props.author, (author) => {
  Object.assign(form, emptyForm(), {
    given_name: author?.given_name ?? '',
    middle_name: author?.middle_name ?? '',
    family_name: author?.family_name ?? '',
    display_name: author?.display_name ?? '',
    orcid: author?.orcid ?? '',
    phone_country_code: author?.phone_country_code ?? '',
    phone_number: author?.phone_number ?? '',
    status: author?.status ?? 'active',
    notes: author?.notes ?? '',
  })
  errorMessage.value = ''
}, { immediate: true })

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

function submit(): void {
  if (props.submitting) return
  errorMessage.value = ''
  const displayName = form.display_name.trim()
  if (!displayName) {
    errorMessage.value = '请填写显示姓名。'
    return
  }
  if (!form.confirm_identity_change) {
    errorMessage.value = '保存前请确认作者身份。'
    return
  }
  const optionalValues: Record<OptionalAuthorField, string | null> = {
    given_name: nullable(form.given_name),
    middle_name: nullable(form.middle_name),
    family_name: nullable(form.family_name),
    orcid: nullable(form.orcid),
    phone_country_code: nullable(form.phone_country_code),
    phone_number: nullable(form.phone_number),
    notes: nullable(form.notes),
  }
  if (props.author) {
    const payload: AuthorUpdate = {
      display_name: displayName,
      status: form.status,
      confirm_identity_change: true,
    }
    for (const field of Object.keys(optionalValues) as OptionalAuthorField[]) {
      if (hasResponseField(field)) payload[field] = optionalValues[field]
    }
    emit('submit', payload)
  } else {
    emit('submit', {
      ...optionalValues,
      display_name: displayName,
      status: form.status,
      alternate_names: [],
      confirm_identity_change: true,
    })
  }
}
</script>

<template>
  <form class="stacked-form" novalidate @submit.prevent="submit">
    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    <div class="form-grid">
      <label v-if="canEditField('given_name')">名<input v-model="form.given_name" data-test="given-name" maxlength="128"></label>
      <label v-if="canEditField('middle_name')">中间名<input v-model="form.middle_name" maxlength="128"></label>
      <label v-if="canEditField('family_name')">姓<input v-model="form.family_name" maxlength="128"></label>
      <label>显示姓名<input v-model="form.display_name" data-test="display-name" required maxlength="255"></label>
      <label v-if="canEditField('orcid')">ORCID<input v-model="form.orcid" placeholder="0000-0002-1825-0097"></label>
      <label>状态<select v-model="form.status"><option value="active">启用</option><option value="inactive">停用</option></select></label>
      <label v-if="canEditField('phone_country_code')">电话国家代码<input v-model="form.phone_country_code" maxlength="16"></label>
      <label v-if="canEditField('phone_number')">电话号码<input v-model="form.phone_number" maxlength="32"></label>
    </div>
    <label v-if="canEditField('notes')">备注<textarea v-model="form.notes" rows="3"></textarea></label>
    <label class="confirmation-control">
      <input v-model="form.confirm_identity_change" data-test="identity-confirm" type="checkbox">
      我确认该作者身份及以上变更准确无误。
    </label>
    <div class="form-actions">
      <button type="submit" :disabled="submitting">{{ submitting ? '保存中…' : '保存作者' }}</button>
      <button type="button" :disabled="submitting" @click="emit('cancel')">取消</button>
    </div>
  </form>
</template>
