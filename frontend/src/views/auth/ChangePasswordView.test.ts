import ElementPlus from 'element-plus'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { api, setCsrfToken } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import ChangePasswordView from './ChangePasswordView.vue'

const initialUser: User = {
  id: 'u1',
  username: 'admin',
  display_name: 'Admin',
  roles: ['system_admin'],
  status: 'active',
  must_change_password: true,
  last_login_at: null,
}

function success(config: InternalAxiosRequestConfig): AxiosResponse {
  return { data: null, status: 204, statusText: '204', headers: {}, config }
}

function failure(config: InternalAxiosRequestConfig, data: unknown): AxiosError {
  return new AxiosError('Request failed', '500', config, undefined, {
    data,
    status: 500,
    statusText: '500',
    headers: {},
    config,
  })
}

describe('ChangePasswordView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(initialUser, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  afterEach(() => setCsrfToken(null))

  async function mountChangePassword() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/login', name: 'login', component: { template: '<div>Login</div>' } },
        { path: '/change-password', name: 'change-password', component: ChangePasswordView },
      ],
    })
    await router.push('/change-password')
    await router.isReady()
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(initialUser, 'csrf')
    const wrapper = mount(ChangePasswordView, { global: { plugins: [pinia, router, ElementPlus] } })
    await wrapper.get('[data-test="current-password"]').setValue('old-password')
    await wrapper.get('[data-test="new-password"]').setValue('new-long-password')
    await wrapper.get('[data-test="confirm-password"]').setValue('new-long-password')
    return { router, wrapper }
  }

  it('shows the product brand alongside the password form', async () => {
    const { wrapper } = await mountChangePassword()

    const logo = wrapper.get('[data-test="app-logo"]')
    expect(logo.attributes('aria-label')).toBe('学术投稿助手标志')
    expect(wrapper.find('[data-test="current-password"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="new-password"]').exists()).toBe(true)
  })

  it('prevents double submission, sends backend fields, and returns to login', async () => {
    let complete!: (response: AxiosResponse) => void
    adapter.mockImplementation(() => new Promise<AxiosResponse>((resolve) => { complete = resolve }))
    const { router, wrapper } = await mountChangePassword()
    const auth = useAuthStore()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('form').trigger('submit')

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(JSON.parse(String(adapter.mock.calls[0][0].data))).toEqual({
      current_password: 'old-password',
      new_password: 'new-long-password',
    })

    complete(success(adapter.mock.calls[0][0]))
    await flushPromises()
    expect(auth.user).toBeNull()
    expect(auth.csrfToken).toBeNull()
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('shows only a safe error and server Request ID', async () => {
    const requestId = '22222222-2222-4222-8222-222222222222'
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, {
        code: 'INTERNAL_SERVER_ERROR',
        message: 'password_hash=secret\nTraceback: raw stack',
        request_id: requestId,
        details: { stack: 'raw stack' },
      })
    })
    const { wrapper } = await mountChangePassword()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(`请求 ID：${requestId}`)
    expect(wrapper.text()).toContain('无法修改密码')
    expect(wrapper.text()).not.toContain('password_hash')
    expect(wrapper.text()).not.toContain('Traceback')
    expect(wrapper.text()).not.toContain('raw stack')
  })

  it('accepts a six-character new password', async () => {
    adapter.mockImplementation(async (config) => success(config))
    const { wrapper } = await mountChangePassword()
    await wrapper.get('[data-test="new-password"]').setValue('abcdef')
    await wrapper.get('[data-test="confirm-password"]').setValue('abcdef')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(adapter.mock.calls[0][0].data))).toEqual({
      current_password: 'old-password',
      new_password: 'abcdef',
    })
  })

  it('does not submit a five-character new password', async () => {
    const { wrapper } = await mountChangePassword()
    await wrapper.get('[data-test="new-password"]').setValue('abcde')
    await wrapper.get('[data-test="confirm-password"]').setValue('abcde')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('新密码长度须为 6 至 128 个字符')
  })

  it('does not submit mismatched password confirmation', async () => {
    const { wrapper } = await mountChangePassword()
    await wrapper.get('[data-test="confirm-password"]').setValue('different-password')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('两次输入的密码不一致')
  })
})
