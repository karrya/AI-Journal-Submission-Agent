import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { expectSaveSuccessToast } from '../../test/toast'
import UserListView from './UserListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

const managedUser = {
  id: 'u1', username: 'api-user', display_name: 'API User',
  roles: ['submission_operator'], status: 'active', must_change_password: true,
  last_login_at: null, created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }
let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/login', name: 'login', component: { template: '<div />' } }],
})

function mountUser() {
  return mount(UserListView, { global: { plugins: [router] } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().setSession({
    id: 'admin-id', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
    status: 'active', must_change_password: false, last_login_at: null,
  }, 'csrf')
  adapter = vi.fn<AxiosAdapter>()
  api.defaults.adapter = adapter
})

describe('UserListView', () => {
  it('lists filters and paginates users without exposing password fields', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      items: [managedUser], page: 1, page_size: 20, total: 21,
    }))
    const wrapper = mountUser()
    await flushPromises()
    expect(wrapper.text()).toContain('api-user')
    expect(wrapper.text()).toContain('投稿操作员')
    expect(wrapper.text()).not.toContain('password_hash')
    await wrapper.get('[data-test="user-status-filter"]').setValue('active')
    await wrapper.get('[data-test="apply-user-filters"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ status: 'active', page: 1 })
    await wrapper.get('[data-test="next-users"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
  })

  it('creates a user with roles and shows the one-second success toast', async () => {
    vi.useFakeTimers()
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'post' ? managedUser : emptyPage,
    ))
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="add-user"]').trigger('click')
    await wrapper.get('[data-test="new-username"]').setValue('new-user')
    await wrapper.get('[data-test="new-display-name"]').setValue('New User')
    await wrapper.get('[data-test="new-password"]').setValue('Strong-Passphrase-2026!')
    await wrapper.get('[data-test="new-password-confirmation"]').setValue('Strong-Passphrase-2026!')
    await wrapper.get('[data-test="create-role-submission_operator"]').setValue(true)
    await wrapper.get('[data-test="user-create-form"]').trigger('submit')
    await flushPromises()
    const call = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(call?.[0].data))).toEqual({
      username: 'new-user', display_name: 'New User',
      password: 'Strong-Passphrase-2026!',
      password_confirmation: 'Strong-Passphrase-2026!',
      roles: ['submission_operator'],
    })
    expectSaveSuccessToast()
  })

  it('validates password confirmation and roles before creating', async () => {
    adapter.mockImplementation(async (config) => success(config, emptyPage))
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="add-user"]').trigger('click')
    await wrapper.get('[data-test="new-username"]').setValue('new-user')
    await wrapper.get('[data-test="new-display-name"]').setValue('New User')
    await wrapper.get('[data-test="new-password"]').setValue('First-2026!')
    await wrapper.get('[data-test="new-password-confirmation"]').setValue('Second-2026!')
    await wrapper.get('[data-test="user-create-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.text()).toContain('两次输入的密码不一致')

    await wrapper.get('[data-test="new-password-confirmation"]').setValue('First-2026!')
    await wrapper.get('[data-test="user-create-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.text()).toContain('请至少选择一个角色')
  })

  it('loads details and updates name roles and status', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/users/u1' && config.method === 'get') return success(config, managedUser)
      if (config.method === 'patch') return success(config, { ...managedUser, status: 'disabled' })
      return success(config, { ...emptyPage, items: [managedUser], total: 1 })
    })
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="edit-user-u1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-display-name"]').setValue('Updated User')
    await wrapper.get('[data-test="edit-role-author"]').setValue(true)
    await wrapper.get('[data-test="edit-role-submission_operator"]').setValue(false)
    await wrapper.get('[data-test="edit-status"]').setValue('disabled')
    await wrapper.get('[data-test="user-edit-form"]').trigger('submit')
    await flushPromises()
    expect(JSON.parse(String(adapter.mock.calls.find(([config]) => config.method === 'patch')?.[0].data))).toEqual({
      display_name: 'Updated User', roles: ['author'], status: 'disabled',
    })
    expectSaveSuccessToast()
  })

  it('resets another user password and keeps the admin session', async () => {
    const other = { ...managedUser, id: 'u2', username: 'other-user' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/users/u2/reset-password' && config.method === 'post') {
        return success(config, null)
      }
      return success(config, { ...emptyPage, items: [other], total: 1 })
    })
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="reset-user-u2"]').trigger('click')
    await wrapper.get('[data-test="reset-new-password"]').setValue('Reset-Passphrase-2026!')
    await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Reset-Passphrase-2026!')
    await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
    await flushPromises()
    const call = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(call?.[0].data))).toEqual({
      new_password: 'Reset-Passphrase-2026!',
      password_confirmation: 'Reset-Passphrase-2026!',
    })
    expect(useAuthStore().isAuthenticated).toBe(true)
    expectSaveSuccessToast()
  })

  it('clears the local session after resetting the current admin password', async () => {
    const current = { ...managedUser, id: 'admin-id', username: 'admin' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/users/admin-id/reset-password' && config.method === 'post') {
        return success(config, null)
      }
      return success(config, { ...emptyPage, items: [current], total: 1 })
    })
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="reset-user-admin-id"]').trigger('click')
    await wrapper.get('[data-test="reset-new-password"]').setValue('Self-Reset-2026!')
    await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Self-Reset-2026!')
    await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
    await flushPromises()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })

  it('rejects mismatched password confirmation before resetting', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      ...emptyPage, items: [managedUser], total: 1,
    }))
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="reset-user-u1"]').trigger('click')
    await wrapper.get('[data-test="reset-new-password"]').setValue('First-2026!')
    await wrapper.get('[data-test="reset-password-confirmation"]').setValue('Second-2026!')
    await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.text()).toContain('两次输入的密码不一致')
  })

  it('ignores an older edit response that arrives after a newer edit', async () => {
    const second = { ...managedUser, id: 'u2', username: 'second-user', display_name: 'Second User' }
    let finishFirst!: (data: unknown) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/users/u1' && config.method === 'get') {
        return new Promise<AxiosResponse>((resolve) => {
          finishFirst = (data) => resolve(success(config, data))
        })
      }
      if (config.url === '/users/u2' && config.method === 'get') return success(config, second)
      return success(config, { ...emptyPage, items: [managedUser, second], total: 2 })
    })
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="edit-user-u1"]').trigger('click')
    await wrapper.get('[data-test="edit-user-u2"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-test="edit-display-name"]').element as HTMLInputElement).value).toBe('Second User')

    finishFirst(managedUser)
    await flushPromises()
    expect((wrapper.get('[data-test="edit-display-name"]').element as HTMLInputElement).value).toBe('Second User')
  })

  it('does not let a pending edit close a newly opened reset form', async () => {
    const second = { ...managedUser, id: 'u2', username: 'second-user', display_name: 'Second User' }
    let finishFirst!: (data: unknown) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/users/u1' && config.method === 'get') {
        return new Promise<AxiosResponse>((resolve) => {
          finishFirst = (data) => resolve(success(config, data))
        })
      }
      return success(config, { ...emptyPage, items: [managedUser, second], total: 2 })
    })
    const wrapper = mountUser()
    await flushPromises()
    await wrapper.get('[data-test="edit-user-u1"]').trigger('click')
    await wrapper.get('[data-test="reset-user-u2"]').trigger('click')
    expect(wrapper.find('[data-test="user-reset-form"]').exists()).toBe(true)

    finishFirst(managedUser)
    await flushPromises()
    expect(wrapper.find('[data-test="user-reset-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-edit-form"]').exists()).toBe(false)
  })
})
