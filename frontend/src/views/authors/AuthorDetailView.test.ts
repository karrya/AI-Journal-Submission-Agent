import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import AuthorDetailView from './AuthorDetailView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

function forbidden(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError('Forbidden', '403', config, undefined, {
    data: { code: 'PERMISSION_DENIED', message: 'denied' },
    status: 403,
    statusText: '403',
    headers: {},
    config,
  })
}

const baseUser: User = {
  id: 'u1',
  username: 'operator',
  display_name: 'Operator',
  roles: ['submission_operator'],
  status: 'active',
  must_change_password: false,
  last_login_at: null,
}

function author(id: string, displayName: string) {
  return {
    id,
    display_name: displayName,
    alternate_names: [],
    status: 'active',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  }
}

const emptyPage = { items: [], page: 1, page_size: 100, total: 0 }
const address = (local: string) => `${local}@example.org`

function emailRecord() {
  return {
    id: 'e1', author_id: 'a1', email: address('author'), normalized_email: address('author'),
    purpose: 'communication', is_primary: false, verification_status: 'unverified',
    authorization_status: 'unconfirmed', created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  }
}

function linkRecord() {
  return {
    id: 'l1', author_id: 'a1', institution_id: 'i1', institution_name: 'Summary University',
    department: 'Research', position_title: null, valid_from: null, valid_to: null,
    is_current: true, display_order: 0, created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  }
}

const stubs = { RouterLink: { template: '<a><slot /></a>' } }

describe('AuthorDetailView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(baseUser, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  afterEach(() => vi.restoreAllMocks())

  it('requests only resources allowed by the current permission set', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Profile Author'))
      if (config.url === '/authors/a1/institutions') return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, {
      global: { stubs },
      props: { authorId: 'a1', permissions: ['author:profile:read'] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Profile Author')
    expect(adapter.mock.calls.map(([config]) => config.url)).toEqual([
      '/authors/a1',
      '/authors/a1/institutions',
    ])
    expect(wrapper.text()).toContain('Email permission is not available')
  })

  it('clears stale emails when a later author email request is forbidden', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'First Author'))
      if (config.url === '/authors/a2') return success(config, author('a2', 'Second Author'))
      if (config.url === '/authors/a1/emails') {
        return success(config, {
          items: [{
            id: 'e1', author_id: 'a1', email: 'old@example.org', normalized_email: 'old@example.org',
            purpose: 'communication', is_primary: true, verification_status: 'verified',
            authorization_status: 'authorized', created_at: '2026-11-01T00:00:00Z',
            updated_at: '2026-11-01T00:00:00Z',
          }],
          page: 1, page_size: 100, total: 1,
        })
      }
      if (config.url === '/authors/a2/emails') throw forbidden(config)
      if (config.url?.endsWith('/institutions')) return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('old@example.org')

    await wrapper.setProps({ authorId: 'a2' })
    await flushPromises()

    expect(wrapper.text()).toContain('Second Author')
    expect(wrapper.text()).not.toContain('old@example.org')
    expect(wrapper.text()).toContain('Emails are not available for this author')
  })

  it('does not render phone fields omitted by the API', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Minimal Author'))
      if (config.url?.endsWith('/emails') || config.url?.endsWith('/institutions')) {
        return success(config, emptyPage)
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('Phone country code')
    expect(wrapper.text()).not.toContain('Phone number')
    expect(wrapper.text()).not.toContain('undefined')
    expect(wrapper.text()).not.toContain('null')
  })

  it('submits an explicitly confirmed email binding and refreshes emails', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1' && config.method === 'get') {
        return success(config, author('a1', 'Email Author'))
      }
      if (config.url === '/authors/a1/emails' && config.method === 'get') {
        return success(config, emptyPage)
      }
      if (config.url === '/authors/a1/emails' && config.method === 'post') {
        return success(config, {})
      }
      if (config.url === '/authors/a1/institutions') return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="new-email"]').setValue(address('new'))
    await wrapper.get('[data-test="create-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="create-email-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(createCall).toBeDefined()
    expect(JSON.parse(String(createCall?.[0].data))).toEqual({
      email: address('new'), purpose: 'communication', is_primary: false,
      confirm_email_binding: true,
    })
    expect(adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/emails' && config.method === 'get')).toHaveLength(2)
  })

  it('loads summary institutions on demand and creates a confirmed affiliation', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1' && config.method === 'get') {
        return success(config, author('a1', 'Affiliated Author'))
      }
      if (config.url === '/authors/a1/emails') return success(config, emptyPage)
      if (config.url === '/authors/a1/institutions' && config.method === 'get') {
        return success(config, emptyPage)
      }
      if (config.url === '/authors/a1/institutions' && config.method === 'post') {
        return success(config, {})
      }
      if (config.url === '/institutions') {
        return success(config, {
          items: [{ id: 'i1', name: 'Summary University', city: 'Beijing', country_code: 'CN' }],
          page: 1, page_size: 100, total: 1,
        })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.url === '/institutions')).toBe(false)

    await wrapper.get('[data-test="add-affiliation"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="institution-select"]').setValue('i1')
    await wrapper.get('[data-test="affiliation-confirm"]').setValue(true)
    await wrapper.get('form[data-test="affiliation-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post' && config.url === '/authors/a1/institutions')
    expect(createCall).toBeDefined()
    const payload = JSON.parse(String(createCall?.[0].data)) as Record<string, unknown>
    expect(payload).toMatchObject({ institution_id: 'i1', display_order: 0 })
    expect(payload).not.toHaveProperty('confirm_affiliation_change')
    expect(payload).not.toHaveProperty('address_line1')
  })

  it('updates the author identity only through the confirmed edit form', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1' && config.method === 'get') {
        return success(config, author('a1', 'Original Name'))
      }
      if (config.url === '/authors/a1' && config.method === 'patch') {
        return success(config, author('a1', 'Confirmed Name'))
      }
      if (config.url === '/authors/a1/emails' || config.url === '/authors/a1/institutions') {
        return success(config, emptyPage)
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-author"]').trigger('click')
    await wrapper.get('[data-test="display-name"]').setValue('Confirmed Name')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('[data-test="author-edit-form"]').trigger('submit')
    await flushPromises()

    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch' && config.url === '/authors/a1')
    const payload = JSON.parse(String(updateCall?.[0].data)) as Record<string, unknown>
    expect(payload).toMatchObject({ display_name: 'Confirmed Name', confirm_identity_change: true })
    expect(payload).not.toHaveProperty('id')
    expect(wrapper.text()).toContain('Confirmed Name')
  })

  it('updates and unbinds emails with their explicit confirmations', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Email Author'))
      if (config.url === '/authors/a1/institutions') return success(config, emptyPage)
      if (config.url === '/authors/a1/emails' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [emailRecord()], total: 1 })
      }
      if (config.url === '/authors/a1/emails/e1' && ['patch', 'delete'].includes(config.method ?? '')) {
        return success(config, config.method === 'patch' ? emailRecord() : null)
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-email-e1"]').trigger('click')
    await wrapper.get('[data-test="edit-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="edit-email-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="delete-email-e1"]').trigger('click')
    await wrapper.get('[data-test="delete-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-e1"]').trigger('click')
    await flushPromises()

    const patchCall = adapter.mock.calls.find(([config]) => config.method === 'patch' && config.url === '/authors/a1/emails/e1')
    expect(JSON.parse(String(patchCall?.[0].data))).toMatchObject({ confirm_email_binding: true })
    const deleteCall = adapter.mock.calls.find(([config]) => config.method === 'delete' && config.url === '/authors/a1/emails/e1')
    expect(JSON.parse(String(deleteCall?.[0].data))).toEqual({ confirm_email_binding: true })
  })

  it('updates and removes affiliations with separate confirmations', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Affiliated Author'))
      if (config.url === '/authors/a1/emails') return success(config, emptyPage)
      if (config.url === '/authors/a1/institutions' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [linkRecord()], total: 1 })
      }
      if (config.url === '/authors/a1/institutions/l1' && ['patch', 'delete'].includes(config.method ?? '')) {
        return success(config, config.method === 'patch' ? linkRecord() : null)
      }
      if (config.url === '/institutions') {
        return success(config, {
          items: [{ id: 'i1', name: 'Summary University', city: 'Beijing', country_code: 'CN' }],
          page: 1, page_size: 100, total: 1,
        })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-affiliation-l1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="department"]').setValue('Updated Department')
    await wrapper.get('[data-test="affiliation-confirm"]').setValue(true)
    await wrapper.get('form[data-test="affiliation-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="delete-affiliation-l1"]').trigger('click')
    await wrapper.get('[data-test="affiliation-delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-affiliation-l1"]').trigger('click')
    await flushPromises()

    const patchCall = adapter.mock.calls.find(([config]) => config.method === 'patch' && config.url === '/authors/a1/institutions/l1')
    expect(JSON.parse(String(patchCall?.[0].data))).toMatchObject({
      institution_id: 'i1', department: 'Updated Department',
    })
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/authors/a1/institutions/l1')).toBe(true)
  })

  it('clears protected data when the current permission set loses email access', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Permission Author'))
      if (config.url === '/authors/a1/emails') {
        return success(config, { ...emptyPage, items: [emailRecord()], total: 1 })
      }
      if (config.url === '/authors/a1/institutions') return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    expect(wrapper.text()).toContain(address('author'))

    await wrapper.setProps({ permissions: ['author:profile:read'] })
    await flushPromises()

    expect(wrapper.text()).not.toContain(address('author'))
    expect(wrapper.text()).toContain('Email permission is not available')
    expect(adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/emails')).toHaveLength(1)

    await wrapper.setProps({ permissions: ['author:profile:read', 'author:email:read'] })
    await flushPromises()
    expect(adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/emails')).toHaveLength(2)
    expect(wrapper.text()).toContain(address('author'))
  })
})
