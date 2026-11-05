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

    expect(wrapper.text()).toContain(`Request ID: ${requestId}`)
    expect(wrapper.text()).toContain('Unable to change password')
    expect(wrapper.text()).not.toContain('password_hash')
    expect(wrapper.text()).not.toContain('Traceback')
    expect(wrapper.text()).not.toContain('raw stack')
  })

  it('does not submit mismatched password confirmation', async () => {
    const { wrapper } = await mountChangePassword()
    await wrapper.get('[data-test="confirm-password"]').setValue('different-password')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Passwords do not match')
  })
})
