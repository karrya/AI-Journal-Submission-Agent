import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AppConfirmDialog from './AppConfirmDialog.vue'

async function mountConfirm(props: Record<string, unknown> = {}, slots = {}) {
  const wrapper = mount(AppConfirmDialog, {
    props: {
      modelValue: true,
      title: '删除作者',
      description: '历史记录保留，当前资料将从列表移除。',
      confirmed: false,
      ...props,
    },
    slots,
    global: { stubs: { teleport: true, transition: false } },
    attachTo: document.body,
  })
  await nextTick()
  return wrapper
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('AppConfirmDialog', () => {
  it('requires explicit confirmation before emitting confirm', async () => {
    const wrapper = await mountConfirm()

    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('删除作者')
    expect(wrapper.get('[data-test="confirm-danger"]').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ confirmed: true })
    await wrapper.get('[data-test="confirm-danger"]').trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('resets confirmation and closes through cancel', async () => {
    const wrapper = await mountConfirm({ confirmed: true })

    await wrapper.get('[data-test="confirm-cancel"]').trigger('click')

    expect(wrapper.emitted('update:confirmed')).toEqual([[false]])
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('locks confirmation and close controls while busy', async () => {
    const wrapper = await mountConfirm({ confirmed: true, busy: true })

    expect(wrapper.get('[data-test="confirm-danger"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.el-dialog__close').exists()).toBe(false)
  })

  it('keeps failure context visible', async () => {
    const wrapper = await mountConfirm({ error: '无法删除，请求 ID：req-2' })

    expect(wrapper.get('[role="alert"]').text()).toContain('无法删除，请求 ID：req-2')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
