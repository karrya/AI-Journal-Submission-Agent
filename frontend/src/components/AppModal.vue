<script setup lang="ts">
import { nextTick, useId, watch } from 'vue'
import { ElDialog, ElMessageBox } from 'element-plus'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  width?: string
  wide?: boolean
  busy?: boolean | (() => boolean)
  dirty?: boolean | (() => boolean)
  error?: string
}>(), {
  description: '',
  width: '640px',
  wide: false,
  busy: false,
  dirty: false,
  error: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  cancel: []
}>()

const titleId = `app-modal-title-${useId()}`
let triggerElement: HTMLElement | null = null

defineExpose({ requestClose })

function isDirty(): boolean {
  return typeof props.dirty === 'function' ? props.dirty() : props.dirty
}

function isBusy(): boolean {
  return typeof props.busy === 'function' ? props.busy() : props.busy
}

async function requestClose(): Promise<void> {
  if (isBusy()) return
  if (isDirty()) {
    try {
      await ElMessageBox.confirm(
        '关闭后将丢失未保存的修改。',
        '放弃未保存的修改？',
        {
          confirmButtonText: '放弃修改',
          cancelButtonText: '继续编辑',
          type: 'warning',
        },
      )
    } catch {
      return
    }
  }
  emit('update:modelValue', false)
  emit('cancel')
}

function focusFirstField(): void {
  void nextTick(() => {
    const dialog = document.getElementById(titleId)?.closest('[role="dialog"]')
    const field = dialog?.querySelector<HTMLElement>(
      'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled])',
    ) ?? dialog?.querySelector<HTMLElement>('button:not([disabled])')
    field?.focus()
  })
}

function restoreTriggerFocus(): void {
  void nextTick(() => {
    if (triggerElement?.isConnected) triggerElement.focus()
  })
}

watch(() => props.modelValue, (open) => {
  if (open) {
    triggerElement = document.activeElement as HTMLElement | null
    focusFirstField()
  } else {
    restoreTriggerFocus()
  }
}, { immediate: true })
</script>

<template>
  <el-dialog
    v-if="modelValue"
    class="app-dialog"
    :class="{ 'app-dialog--wide': wide }"
    :model-value="modelValue"
    append-to-body
    align-center
    :title="title"
    :width="width"
    :close-on-click-modal="false"
    :close-on-press-escape="busy !== true"
    :show-close="busy !== true"
    :before-close="requestClose"
    :aria-labelledby="titleId"
    @focus-after-trapped="focusFirstField"
    @opened="focusFirstField"
    @close-auto-focus="restoreTriggerFocus"
  >
    <template #header>
      <header class="app-dialog__header">
        <span class="app-dialog__accent" aria-hidden="true" />
        <div>
          <h2 :id="titleId">{{ title }}</h2>
          <p v-if="description">{{ description }}</p>
        </div>
      </header>
    </template>

    <div class="app-dialog__body">
      <p v-if="wide" class="app-dialog__scroll-hint">表单较长时可滚动查看全部内容</p>
      <p v-if="error" class="form-error app-dialog__error" role="alert">{{ error }}</p>
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <div class="app-dialog__footer"><slot name="footer" /></div>
    </template>
  </el-dialog>
</template>
