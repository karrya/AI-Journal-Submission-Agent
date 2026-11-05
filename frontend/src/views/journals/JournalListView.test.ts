import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import JournalListView from './JournalListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

const admin: User = {
  id: 'u1', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const publisher = {
  id: 'p1', name: 'Publisher One', website_url: 'https://publisher.example', notes: null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const platform = {
  id: 's1', code: 'OJS', name: 'Open Journal Systems', description: '', status: 'active',
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const journal = {
  id: 'j1', publisher_id: 'p1', platform_id: 's1', name: 'Journal One', issn: '03785955',
  eissn: null, website_url: 'https://journal.example', submission_url: null,
  author_guidelines_url: null, subject_categories: [], article_types: [], requirements: [],
  requirements_source_url: null, requirements_verified_at: null, status: 'active', notes: null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const page = (items: object[], total = items.length) => ({ items, page: 1, page_size: 20, total })

describe('JournalListView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(admin, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  function resource(config: InternalAxiosRequestConfig): object[] {
    if (config.url === '/publishers') return [publisher]
    if (config.url === '/journal-platforms') return [platform]
    return [journal]
  }

  it('uses server pagination and allowlisted sorting for all three tables', async () => {
    adapter.mockImplementation(async (config) => success(config, page(resource(config), 21)))
    const wrapper = mount(JournalListView)
    await flushPromises()
    await wrapper.get('[data-test="next-publishers"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
    await wrapper.get('[data-test="publisher-sort"]').setValue('created_at')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 1, sort: 'created_at' })
    expect(wrapper.get('[data-test="publisher-sort"]').html()).not.toContain('created_by')

    await wrapper.get('[data-test="platforms-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="next-platforms"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
    await wrapper.get('[data-test="platform-sort"]').setValue('name')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ sort: 'name' })

    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="next-journals"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
    await wrapper.get('[data-test="journal-sort"]').setValue('updated_at')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ sort: 'updated_at' })
    expect(wrapper.text()).toContain('0378-5955')
  })

  it('shows a specific empty state for every resource', async () => {
    adapter.mockImplementation(async (config) => success(config, page([])))
    const wrapper = mount(JournalListView)
    await flushPromises()
    expect(wrapper.text()).toContain('No publishers found')
    await wrapper.get('[data-test="platforms-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No platforms found')
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No journals found')
  })

  it('creates and updates publishers with separate request models', async () => {
    adapter.mockImplementation(async (config) => success(config,
      ['post', 'patch'].includes(config.method ?? '') ? publisher : page([publisher]),
    ))
    const wrapper = mount(JournalListView)
    await flushPromises()
    await wrapper.get('[data-test="add-publisher"]').trigger('click')
    await wrapper.get('[data-test="publisher-name"]').setValue('New Publisher')
    await wrapper.get('[data-test="publisher-form"]').trigger('submit')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({ name: 'New Publisher' })

    await wrapper.get('[data-test="edit-publisher-p1"]').trigger('click')
    await wrapper.get('[data-test="publisher-name"]').setValue('Updated Publisher')
    await wrapper.get('[data-test="publisher-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(updateCall?.[0].url).toBe('/publishers/p1')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({ name: 'Updated Publisher' })
  })

  it('creates and updates journal platforms', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([]))
      if (['post', 'patch'].includes(config.method ?? '')) return success(config, platform)
      return success(config, page([platform]))
    })
    const wrapper = mount(JournalListView)
    await flushPromises()
    await wrapper.get('[data-test="platforms-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-platform"]').trigger('click')
    await wrapper.get('[data-test="platform-code"]').setValue('OJS')
    await wrapper.get('[data-test="platform-name"]').setValue('Open Journal Systems')
    await wrapper.get('[data-test="platform-form"]').trigger('submit')
    await flushPromises()
    expect(JSON.parse(String(adapter.mock.calls.find(([config]) => config.method === 'post')?.[0].data))).toMatchObject({ code: 'OJS', status: 'active' })

    await wrapper.get('[data-test="edit-platform-s1"]').trigger('click')
    await wrapper.get('[data-test="platform-name"]').setValue('Updated Platform')
    await wrapper.get('[data-test="platform-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(updateCall?.[0].url).toBe('/journal-platforms/s1')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({ name: 'Updated Platform' })
  })

  it('requires every journal requirement field and an HTTPS source', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([publisher]))
      if (config.url === '/journal-platforms') return success(config, page([platform]))
      if (config.url === '/journals' && config.method === 'get') return success(config, page([journal]))
      if (['post', 'patch'].includes(config.method ?? '')) return success(config, journal)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView)
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-journal"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="journal-name"]').setValue('New Journal')
    await wrapper.get('[data-test="journal-publisher"]').setValue('p1')
    await wrapper.get('[data-test="add-requirement"]').trigger('click')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.text()).toContain('Requirement key, value, scope, HTTPS source URL, and verification time are required')

    await wrapper.get('[data-test="requirement-key"]').setValue('abstract_words')
    await wrapper.get('[data-test="requirement-value"]').setValue('250')
    await wrapper.get('[data-test="requirement-scope"]').setValue('research')
    await wrapper.get('[data-test="requirement-source"]').setValue('http://journal.example/guide')
    await wrapper.get('[data-test="requirement-verified"]').setValue('2026-11-04T00:00')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.text()).toContain('HTTPS')

    await wrapper.get('[data-test="requirement-source"]').setValue('https://journal.example/guide')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    const payload = JSON.parse(String(createCall?.[0].data)) as { requirements: object[] }
    expect(payload.requirements).toEqual([{
      key: 'abstract_words', value: '250', scope: 'research',
      source_url: 'https://journal.example/guide',
      verified_at: new Date('2026-11-04T00:00').toISOString(),
    }])

    await wrapper.get('[data-test="edit-journal-j1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="journal-name"]').setValue('Updated Journal')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(updateCall?.[0].url).toBe('/journals/j1')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({ name: 'Updated Journal' })
  })

  it('requires separate soft-delete confirmation for publishers, platforms, and journals', async () => {
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'delete' ? null : page(resource(config)),
    ))
    const wrapper = mount(JournalListView)
    await flushPromises()
    await wrapper.get('[data-test="delete-publisher-p1"]').trigger('click')
    await wrapper.get('[data-test="confirm-delete-publisher-p1"]').trigger('click')
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete')).toBe(false)
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-publisher-p1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/publishers/p1')).toBe(true)

    await wrapper.get('[data-test="platforms-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="delete-platform-s1"]').trigger('click')
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-platform-s1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/journal-platforms/s1')).toBe(true)

    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="delete-journal-j1"]').trigger('click')
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-journal-j1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/journals/j1')).toBe(true)
  })
})
