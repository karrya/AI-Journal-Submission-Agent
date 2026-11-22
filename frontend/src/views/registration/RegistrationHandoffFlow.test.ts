import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import RegistrationView from './RegistrationView.vue'

const now = '2026-11-22T00:00:00Z'
const operator: User = {
  id: 'operator-1', username: 'operator', display_name: 'Operator', roles: ['submission_operator'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const handoffTask = {
  id: 'task-1', author_id: 'a1', publisher_id: 'p1', journal_id: 'j1', platform_code: 'EM',
  task_status: 'NEEDS_MANUAL_REVIEW', current_step: 'HANDOFF_CAPTCHA', retryable: false, created_at: now,
}
const handoff = {
  task_id: 'task-1', reason: '需要完成验证码', manual_url: 'https://register.example/start',
  browser_handoff_id: 'handoff-1', current_step: 'HANDOFF_CAPTCHA',
}

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

describe('Registration handoff flow', () => {
  it('opens the official page, resumes the same task, and stops polling after unmount', async () => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    useAuthStore().setSession(operator, 'csrf')
    let currentTask = { ...handoffTask }
    const adapter = vi.fn<AxiosAdapter>(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [] })
      if (config.url === '/registration/tasks') return success(config, { items: [currentTask], page: 1, page_size: 20, total: 1 })
      if (config.url === '/registration/tasks/task-1/handoff') return success(config, handoff)
      if (config.method === 'post' && config.url === '/registration/tasks/task-1/resume') {
        currentTask = { ...handoffTask, task_status: 'PENDING', current_step: 'HANDOFF_RESUMED' }
        return success(config, currentTask)
      }
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    api.defaults.adapter = adapter
    vi.stubGlobal('open', vi.fn())
    const wrapper = mount(RegistrationView, {
      attachTo: document.body,
      global: { stubs: { teleport: true, transition: false } },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(wrapper.get('[data-test="registration-handoff-dialog"]').exists()).toBe(true)
    await wrapper.get('[data-test="open-manual-page"]').trigger('click')
    expect(window.open).toHaveBeenCalledWith(handoff.manual_url, '_blank', 'noopener,noreferrer')
    await wrapper.get('[data-test="resume-registration"]').trigger('click')
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => config.method === 'post' && config.url === '/registration/tasks/task-1/resume')).toBe(true)
    expect(wrapper.find('[data-test="registration-handoff-dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="open-create-registration"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('待执行')
    const callsAfterResume = adapter.mock.calls.length
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(5000)
    expect(adapter.mock.calls.length).toBe(callsAfterResume)
    vi.useRealTimers()
  })
})
