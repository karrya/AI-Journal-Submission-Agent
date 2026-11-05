import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import AuthorDetailView from './AuthorDetailView.vue'
import EmailTable from '../../components/EmailTable.vue'

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

function emailRecord(authorId = 'a1', local = 'author') {
  return {
    id: authorId === 'a1' && local === 'author' ? 'e1' : `e-${authorId}-${local}`, author_id: authorId, email: address(local), normalized_email: address(local),
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
    expect(wrapper.text()).not.toContain('No emails.')
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

  it('does not apply an in-flight author save after navigating to another author', async () => {
    let finishPatch!: (response: AxiosResponse) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1' && config.method === 'get') return success(config, author('a1', 'Author A'))
      if (config.url === '/authors/a2' && config.method === 'get') return success(config, author('a2', 'Author B'))
      if (config.url === '/authors/a1' && config.method === 'patch') {
        return new Promise<AxiosResponse>((resolve) => { finishPatch = resolve })
      }
      if (config.url?.endsWith('/emails') || config.url?.endsWith('/institutions')) return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-author"]').trigger('click')
    await wrapper.get('[data-test="display-name"]').setValue('Stale Author A')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('[data-test="author-edit-form"]').trigger('submit')
    await vi.waitFor(() => expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(true))

    await wrapper.setProps({ authorId: 'a2' })
    await flushPromises()
    const patchConfig = adapter.mock.calls.find(([config]) => config.method === 'patch')?.[0]
    finishPatch(success(patchConfig!, author('a1', 'Stale Author A')))
    await flushPromises()

    expect(wrapper.text()).toContain('Author B')
    expect(wrapper.text()).not.toContain('Stale Author A')
  })

  it('does not restore author A emails after an in-flight refresh follows navigation to B', async () => {
    let finishRefresh!: (response: AxiosResponse) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Author A'))
      if (config.url === '/authors/a2') return success(config, author('a2', 'Author B'))
      if (config.url === '/authors/a1/emails' && config.method === 'post') return success(config, emailRecord())
      if (config.url === '/authors/a1/emails') {
        const refreshCount = adapter.mock.calls.filter(([call]) => call.url === '/authors/a1/emails' && call.method === 'get').length
        if (refreshCount > 1) return new Promise<AxiosResponse>((resolve) => { finishRefresh = resolve })
        return success(config, emptyPage)
      }
      if (config.url === '/authors/a2/emails') {
        return success(config, { ...emptyPage, items: [emailRecord('a2', 'author-b')], total: 1 })
      }
      if (config.url?.endsWith('/institutions')) return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="new-email"]').setValue(address('new-a'))
    await wrapper.get('[data-test="create-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="create-email-form"]').trigger('submit')
    await vi.waitFor(() => expect(adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/emails' && config.method === 'get')).toHaveLength(2))

    await wrapper.setProps({ authorId: 'a2' })
    await flushPromises()
    const refreshConfig = adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/emails' && config.method === 'get').at(-1)?.[0]
    finishRefresh(success(refreshConfig!, { ...emptyPage, items: [emailRecord('a1', 'stale-a')], total: 1 }))
    await flushPromises()

    expect(wrapper.text()).toContain(address('author-b'))
    expect(wrapper.text()).not.toContain(address('stale-a'))
  })

  it('does not restore author A affiliations after an in-flight refresh follows navigation to B', async () => {
    let finishRefresh!: (response: AxiosResponse) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Author A'))
      if (config.url === '/authors/a2') return success(config, author('a2', 'Author B'))
      if (config.url === '/authors/a1/institutions' && config.method === 'post') return success(config, linkRecord())
      if (config.url === '/authors/a1/institutions') {
        const refreshCount = adapter.mock.calls.filter(([call]) => call.url === '/authors/a1/institutions' && call.method === 'get').length
        if (refreshCount > 1) return new Promise<AxiosResponse>((resolve) => { finishRefresh = resolve })
        return success(config, emptyPage)
      }
      if (config.url === '/authors/a2/institutions') {
        return success(config, { ...emptyPage, items: [{ ...linkRecord(), id: 'b-link', author_id: 'a2', institution_name: 'B University' }], total: 1 })
      }
      if (config.url === '/authors/a1/emails' || config.url === '/authors/a2/emails') return success(config, emptyPage)
      if (config.url === '/institutions') return success(config, { items: [{ id: 'i1', name: 'Summary University' }], page: 1, page_size: 100, total: 1 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="add-affiliation"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="institution-select"]').setValue('i1')
    await wrapper.get('[data-test="affiliation-confirm"]').setValue(true)
    await wrapper.get('form[data-test="affiliation-form"]').trigger('submit')
    await vi.waitFor(() => expect(adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/institutions' && config.method === 'get')).toHaveLength(2))

    await wrapper.setProps({ authorId: 'a2' })
    await flushPromises()
    const refreshConfig = adapter.mock.calls.filter(([config]) => config.url === '/authors/a1/institutions' && config.method === 'get').at(-1)?.[0]
    finishRefresh(success(refreshConfig!, { ...emptyPage, items: [{ ...linkRecord(), institution_name: 'Stale A University' }], total: 1 }))
    await flushPromises()

    expect(wrapper.text()).toContain('B University')
    expect(wrapper.text()).not.toContain('Stale A University')
  })

  it('loads every institution selector page', async () => {
    const choices = Array.from({ length: 101 }, (_, index) => ({ id: `i${index}`, name: `Institution ${index}` }))
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Selector Author'))
      if (config.url === '/authors/a1/emails' || config.url === '/authors/a1/institutions') return success(config, emptyPage)
      if (config.url === '/institutions') {
        const page = Number(config.params?.page ?? 1)
        return success(config, { items: choices.slice((page - 1) * 100, page * 100), page, page_size: 100, total: choices.length })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="add-affiliation"]').trigger('click')
    await flushPromises()

    const institutionCalls = adapter.mock.calls.filter(([config]) => config.url === '/institutions')
    expect(institutionCalls.map(([config]) => config.params.page)).toEqual([1, 2])
    expect(wrapper.get('[data-test="institution-select"]').find('option[value="i100"]').exists()).toBe(true)
  })

  it('preserves the current affiliation when it is absent from selector pages', async () => {
    const currentLink = { ...linkRecord(), institution_id: 'missing-i', institution_name: 'Current Missing Institution' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Selector Author'))
      if (config.url === '/authors/a1/emails') return success(config, emptyPage)
      if (config.url === '/authors/a1/institutions') return success(config, { ...emptyPage, items: [currentLink], total: 1 })
      if (config.url === '/institutions') return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-affiliation-l1"]').trigger('click')
    await flushPromises()

    const select = wrapper.get('[data-test="institution-select"]')
    expect((select.element as HTMLSelectElement).value).toBe('missing-i')
    expect(select.text()).toContain('Current Missing Institution')
  })

  it('keeps existing emails and management controls available for retry after a rejected mutation', async () => {
    let updateAttempts = 0
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Retry Author'))
      if (config.url === '/authors/a1/emails' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [emailRecord()], total: 1 })
      }
      if (config.url === '/authors/a1/emails/e1' && config.method === 'patch') {
        updateAttempts += 1
        if (updateAttempts === 1) throw new Error('Transient update failure')
        return success(config, emailRecord())
      }
      if (config.url === '/authors/a1/institutions') return success(config, emptyPage)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-email-e1"]').trigger('click')
    await wrapper.get('[data-test="edit-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="edit-email-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Unable to update the email binding')
    expect(wrapper.text()).toContain(address('author'))
    expect(wrapper.find('[data-test="edit-email-e1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="edit-email-form"]').exists()).toBe(true)

    await wrapper.get('[data-test="edit-email-form"]').trigger('submit')
    await flushPromises()
    expect(updateAttempts).toBe(2)
    expect(wrapper.text()).toContain(address('author'))
  })

  it('retries institution option loading after a preserved-fallback failure', async () => {
    let optionAttempts = 0
    const currentLink = { ...linkRecord(), institution_id: 'missing-i', institution_name: 'Current Missing Institution' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors/a1') return success(config, author('a1', 'Selector Author'))
      if (config.url === '/authors/a1/emails') return success(config, emptyPage)
      if (config.url === '/authors/a1/institutions') return success(config, { ...emptyPage, items: [currentLink], total: 1 })
      if (config.url === '/institutions') {
        optionAttempts += 1
        if (optionAttempts === 1) throw new Error('Temporary selector failure')
        return success(config, { items: [{ id: 'i1', name: 'Recovered Institution' }], page: 1, page_size: 100, total: 1 })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(AuthorDetailView, { global: { stubs }, props: { authorId: 'a1' } })
    await flushPromises()
    await wrapper.get('[data-test="edit-affiliation-l1"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Unable to load institution choices')
    expect((wrapper.get('[data-test="institution-select"]').element as HTMLSelectElement).value).toBe('missing-i')

    await wrapper.get('form[data-test="affiliation-form"] button[type="button"]').trigger('click')
    await wrapper.get('[data-test="edit-affiliation-l1"]').trigger('click')
    await flushPromises()

    expect(optionAttempts).toBe(2)
    expect(wrapper.get('[data-test="institution-select"]').find('option[value="i1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Recovered Institution')
  })

  it('rechecks manage permission for emitted email mutations after access is lost', async () => {
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
    await wrapper.get('[data-test="edit-email-e1"]').trigger('click')
    await wrapper.setProps({ permissions: ['author:profile:read', 'author:email:read'] })
    await flushPromises()
    expect(wrapper.find('[data-test="edit-email-form"]').exists()).toBe(false)

    const table = wrapper.findComponent(EmailTable)
    table.vm.$emit('create', { email: address('blocked'), purpose: 'communication', is_primary: false, confirm_email_binding: true })
    table.vm.$emit('update', { emailId: 'e1', payload: { purpose: 'backup', confirm_email_binding: true } })
    table.vm.$emit('delete', { emailId: 'e1', confirm_email_binding: true })
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => ['post', 'patch', 'delete'].includes(config.method ?? ''))).toBe(false)
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
