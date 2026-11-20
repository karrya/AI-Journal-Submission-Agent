<script setup lang="ts">
import { useId } from 'vue'
import { ElDialog } from 'element-plus'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description: string
  confirmed: boolean
  confirmationText?: string
  confirmLabel?: string
  confirmTest?: string
  confirmationTest?: string
  busy?: boolean
  error?: string
}>(), {
  confirmationText: '我已了解后果并确认执行。',
  confirmLabel: '确认删除',
  busy: false,
  error: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:confirmed': [value: boolean]
  confirm: []
  cancel: []
}>()

const titleId = `app-confirm-title-${useId()}`

function requestClose(): void {
  if (props.busy) return
  emit('update:confirmed', false)
  emit('update:modelValue', false)
  emit('cancel')
}

function confirmAction(): void {
  if (props.busy || !props.confirmed) return
  emit('confirm')
}
</script>

<template>
  <el-dialog
    v-if="modelValue"
    class="app-dialog app-confirm"
    :model-value="modelValue"
    :title="title"
    width="480px"
    top="12vh"
    :close-on-click-modal="false"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    :before-close="requestClose"
    :aria-labelledby="titleId"
  >
    <template #header>
      <header class="app-dialog__header app-confirm__header">
        <span class="app-confirm__icon" aria-hidden="true">!</span>
        <div>
          <h2 :id="titleId">{{ title }}</h2>
          <p>{{ description }}</p>
        </div>
      </header>
    </template>

    <div class="app-dialog__body">
      <slot />
      <p v-if="error" class="form-error app-dialog__error" role="alert">{{ error }}</p>
      <label class="confirmation-control app-confirm__control">
        <input
          :checked="confirmed"
          :data-test="confirmationTest ?? 'danger-confirmation'"
          type="checkbox"
          :disabled="busy"
          @change="emit('update:confirmed', ($event.target as HTMLInputElement).checked)"
        >
        {{ confirmationText }}
      </label>
    </div>

    <template #footer>
      <div class="app-dialog__footer">
        <button class="action-button action-button--neutral" data-test="confirm-cancel" type="button" :disabled="busy" @click="requestClose">取消</button>
        <button class="action-button action-button--danger" :data-test="confirmTest ?? 'confirm-danger'" type="button" :disabled="!confirmed || busy" @click="confirmAction">
          {{ busy ? '处理中…' : confirmLabel }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>
