<script setup lang="ts">
import AppModal from './AppModal.vue'
import type { RegistrationHandoff } from '../api/registration'

const props = withDefaults(defineProps<{
  handoff: RegistrationHandoff
  busy?: boolean
}>(), {
  busy: false,
})

const emit = defineEmits<{
  resume: [taskId: string]
  cancel: []
}>()

function openManualPage(): void {
  window.open(props.handoff.manual_url, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <AppModal
    :model-value="true"
    title="需要人工接管"
    description="自动步骤已暂停，已填写的内容会保留。处理完成后可继续执行。"
    :busy="busy"
    @cancel="emit('cancel')"
  >
    <div data-test="registration-handoff-dialog">
      <p>{{ handoff.reason }}</p>
      <p>请只在官方页面完成人工步骤，不要在弹窗中输入密码或验证码。</p>
      <button class="text-button" type="button" data-test="open-manual-page" @click="openManualPage">打开人工处理页面</button>
    </div>
    <template #footer>
      <button class="action-button action-button--create" type="button" data-test="resume-registration" :disabled="busy" @click="emit('resume', handoff.task_id)">
        {{ busy ? '正在恢复…' : '处理完毕，继续执行' }}
      </button>
    </template>
  </AppModal>
</template>
