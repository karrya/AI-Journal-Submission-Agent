import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { PERMISSION_CODES, type AuthorizationResponse } from '../../api/authors'
import { useAuthStore, type User } from '../../stores/auth'
import AuthorizationView from './AuthorizationView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

const admin: User = {
  id: 'admin-id', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
  status: 'active', must_change_password: false, last_login_at: null,
}

const authorization: AuthorizationResponse = {
  id: 'z1', author_id: 'a1', user_id: 'user-1', permissions: ['author:profile:read'],
  valid_from: '2026-11-01T00:00:00Z', valid_to: '2099-11-02T00:00:00Z',
  evidence_ref: null, notes: null, revoked_at: null, reviewed_by: 'admin-id',
  reviewed_at: '2026-11-01T00:00:00Z', created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z', validity_status: 'active',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }

describe('AuthorizationView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(admin, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  function mountView() {
    return mount(AuthorizationView, { props: { authorId: 'a1' } })
  }

  it('offers exactly the nine permissions and creates a finite authorization', async () => {
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'post' ? authorization : emptyPage,
    ))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="add-authorization"]').trigger('click')
    const options = wrapper.findAll('[data-test="permission-option"]')
    expect(options).toHaveLength(9)
    expect(options.map((option) => option.attributes('value'))).toEqual([...PERMISSION_CODES])

    await wrapper.get('[data-test="authorization-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    await wrapper.get('[data-test="authorization-user-id"]').setValue('user-1')
    await options[0].setValue(true)
    await wrapper.get('[data-test="valid-from"]').setValue('2099-11-01T00:00')
    await wrapper.get('[data-test="valid-to"]').setValue('2099-11-02T00:00')
    await wrapper.get('[data-test="authorization-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(createCall?.[0].url).toBe('/author-authorizations')
    expect(JSON.parse(String(createCall?.[0].data))).toEqual({
      author_id: 'a1', user_id: 'user-1', permissions: ['manuscript:read'],
      valid_from: new Date('2099-11-01T00:00').toISOString(),
      valid_to: new Date('2099-11-02T00:00').toISOString(),
      evidence_ref: null, notes: null,
    })
  })

  it('rejects an inverted or nonfinite interval before update', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      ...emptyPage, items: [authorization], total: 1,
    }))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="edit-authorization-z1"]').trigger('click')
    await wrapper.get('[data-test="valid-from"]').setValue('2099-11-03T00:00')
    await wrapper.get('[data-test="valid-to"]').setValue('2099-11-02T00:00')
    await wrapper.get('[data-test="authorization-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(false)
    expect(wrapper.text()).toContain('结束时间必须晚于开始时间')

    await wrapper.get('[data-test="valid-to"]').setValue('')
    await wrapper.get('[data-test="authorization-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(false)
    expect(wrapper.text()).toContain('请填写开始时间和结束时间')

    await wrapper.get('[data-test="valid-from"]').setValue('2099-11-01T00:00')
    await wrapper.get('[data-test="valid-to"]').setValue('2099-11-04T00:00')
    await wrapper.get('[data-test="authorization-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(updateCall?.[0].url).toBe('/author-authorizations/z1')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({
      permissions: ['author:profile:read'],
      valid_from: new Date('2099-11-01T00:00').toISOString(),
      valid_to: new Date('2099-11-04T00:00').toISOString(),
    })
  })

  it('uses a separate revoke confirmation and never reuses the edit submit', async () => {
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'post' ? { ...authorization, validity_status: 'revoked' } : { ...emptyPage, items: [authorization], total: 1 },
    ))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="revoke-authorization-z1"]').trigger('click')
    await wrapper.get('[data-test="revoke-reason"]').setValue('Access ended')
    await wrapper.get('[data-test="confirm-revoke-z1"]').trigger('click')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)

    await wrapper.get('[data-test="revoke-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-revoke-z1"]').trigger('click')
    await flushPromises()
    const revokeCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(revokeCall?.[0].url).toBe('/author-authorizations/z1/revoke')
    expect(JSON.parse(String(revokeCall?.[0].data))).toEqual({ reason: 'Access ended' })
  })

  it('shows an empty state and uses server pagination', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      items: [], page: 1, page_size: 20, total: 21,
    }))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('未找到授权')
    expect(adapter.mock.calls[0][0].params).toMatchObject({
      author_id: 'a1', page: 1, page_size: 20, sort: 'created_at', order: 'desc',
    })
    await wrapper.get('[data-test="next-authorizations"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
  })

  it('does not show an empty state when authorization loading fails', async () => {
    adapter.mockImplementation(async () => { throw new Error('offline') })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('无法加载授权')
    expect(wrapper.text()).not.toContain('未找到授权')
  })
})
