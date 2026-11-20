import { flushPromises, mount } from '@vue/test-utils'
import { ElMessageBox } from 'element-plus'
import { nextTick } from 'vue'
import AppModal from './AppModal.vue'

async function mountModal(props: Record<string, unknown>, slots = {}) {
  const wrapper = mount(AppModal, {
    props: { modelValue: true, title: '编辑期刊', ...props },
    slots,
    global: { stubs: { teleport: true, transition: false } },
    attachTo: document.body,
  })
  await nextTick()
  return wrapper
}

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('AppModal', () => {
  it('renders an accessible titled dialog and closes cleanly', async () => {
    const wrapper = await mountModal({}, { default: '<input data-test="title-input" />' })

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(dialog.attributes('aria-label')).toBe('编辑期刊')
    expect(wrapper.text()).toContain('编辑期刊')
    expect(wrapper.find('[data-test="title-input"]').exists()).toBe(true)

    await wrapper.get('.el-dialog__close').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('blocks accidental close when dirty and closes after explicit discard', async () => {
    let resolveDiscard!: (value: string) => void
    const discard = new Promise<string>((resolve) => { resolveDiscard = resolve })
    vi.spyOn(ElMessageBox, 'confirm').mockReturnValue(discard as never)
    const wrapper = await mountModal({ dirty: true }, { default: '<input data-test="title-input" />' })

    await wrapper.get('.el-dialog__close').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    resolveDiscard('confirm')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      '关闭后将丢失未保存的修改。',
      '放弃未保存的修改？',
      expect.objectContaining({ confirmButtonText: '放弃修改' }),
    )
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })

  it('keeps the form open when discarding is cancelled', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    const wrapper = await mountModal({ dirty: true })

    await wrapper.get('.el-dialog__close').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('does not expose close controls while busy', async () => {
    const wrapper = await mountModal({ busy: true })

    expect(wrapper.find('.el-dialog__close').exists()).toBe(false)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('focuses the first editable field when opened', async () => {
    const wrapper = await mountModal({}, { default: '<input data-test="title-input" />' })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))

    expect(document.activeElement).toBe(wrapper.get('[data-test="title-input"]').element)
  })

  it('returns focus to the triggering control after close', async () => {
    const trigger = document.createElement('button')
    trigger.id = 'open-journal-modal'
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = await mountModal({})

    await wrapper.get('.el-dialog__close').trigger('click')
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))

    expect(document.activeElement).toBe(trigger)
  })

  it('shows the request error inside the dialog', async () => {
    const wrapper = await mountModal({ error: '无法保存，请求 ID：req-1' })

    expect(wrapper.get('[role="alert"]').text()).toContain('无法保存，请求 ID：req-1')
  })
})
