import ElementPlus from 'element-plus'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { api } from '../../api/client'
import LoginView from './LoginView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
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

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: LoginView },
      { path: '/change-password', name: 'change-password', component: { template: '<div>Change password</div>' } },
      { path: '/dashboard', name: 'dashboard', component: { template: '<div>Dashboard</div>' } },
    ],
  })
}

describe('LoginView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    setActivePinia(createPinia())
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  async function mountLogin() {
    const router = testRouter()
    await router.push('/login')
    await router.isReady()
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(LoginView, { global: { plugins: [pinia, router, ElementPlus] } })
    await wrapper.get('[data-test="username"]').setValue('admin')
    await wrapper.get('[data-test="password"]').setValue('secret')
    return { router, wrapper }
  }

  it('shows the product brand alongside the login form', async () => {
    const { wrapper } = await mountLogin()

    const logo = wrapper.get('[data-test="app-logo"]')
    expect(logo.attributes('aria-label')).toBe('学术投稿助手标志')
    expect(wrapper.find('[data-test="username"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="password"]').exists()).toBe(true)
  })

  it('prevents double submission and uses backend login fields', async () => {
    let complete!: (response: AxiosResponse) => void
    adapter.mockImplementation(() => new Promise<AxiosResponse>((resolve) => { complete = resolve }))
    const { router, wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('form').trigger('submit')

    expect(adapter).toHaveBeenCalledTimes(1)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(JSON.parse(String(adapter.mock.calls[0][0].data))).toEqual({ username: 'admin', password: 'secret' })

    complete(success(adapter.mock.calls[0][0], {
      user: {
        id: 'u1', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
        status: 'active', must_change_password: false, last_login_at: null,
      },
      csrf_token: 'csrf',
      idle_expires_at: '2026-11-05T10:00:00Z',
      absolute_expires_at: '2026-11-05T18:00:00Z',
    }))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('routes first-time users to change-password', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      user: {
        id: 'u1', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
        status: 'active', must_change_password: true, last_login_at: null,
      },
      csrf_token: 'csrf',
      idle_expires_at: '2026-11-05T10:00:00Z',
      absolute_expires_at: '2026-11-05T18:00:00Z',
    }))
    const { router, wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('shows only a safe error and server Request ID', async () => {
    const requestId = '11111111-1111-4111-8111-111111111111'
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, {
        code: 'INTERNAL_SERVER_ERROR',
        message: 'password_hash=secret\nTraceback: raw stack',
        request_id: requestId,
        details: { stack: 'raw stack' },
      })
    })
    const { wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(`请求 ID：${requestId}`)
    expect(wrapper.text()).toContain('无法登录')
    expect(wrapper.text()).not.toContain('password_hash')
    expect(wrapper.text()).not.toContain('Traceback')
    expect(wrapper.text()).not.toContain('raw stack')
  })

  it('does not submit empty credentials', async () => {
    const { wrapper } = await mountLogin()
    await wrapper.get('[data-test="username"]').setValue('')
    await wrapper.get('[data-test="password"]').setValue('')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).not.toHaveBeenCalled()
  })
})
