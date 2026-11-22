import { flushPromises, mount } from '@vue/test-utils'
import RegistrationHandoffDialog from './RegistrationHandoffDialog.vue'

const handoff = {
  task_id: 'task-1',
  reason: '需要完成验证码',
  manual_url: 'https://register.example/start',
  browser_handoff_id: 'handoff-1',
  current_step: 'HANDOFF_CAPTCHA',
}

describe('RegistrationHandoffDialog', () => {
  it('opens the official page and resumes the same task', async () => {
    vi.stubGlobal('open', vi.fn())
    const wrapper = mount(RegistrationHandoffDialog, {
      props: { handoff },
      global: { stubs: { teleport: true, transition: false } },
    })
    await flushPromises()

    await wrapper.get('[data-test="open-manual-page"]').trigger('click')
    expect(window.open).toHaveBeenCalledWith(handoff.manual_url, '_blank', 'noopener,noreferrer')
    await wrapper.get('[data-test="resume-registration"]').trigger('click')
    expect(wrapper.emitted('resume')).toEqual([[handoff.task_id]])
  })
})
