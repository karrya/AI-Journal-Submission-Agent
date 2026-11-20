import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { expectSaveSuccessToast } from '../../test/toast'
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
const platform = 'OJS'
const journal = {
  id: 'j1', publisher_id: 'p1', platform_code: platform, name: 'Journal One', issn: '03785955',
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
    return [journal]
  }

  it('uses server pagination and allowlisted sorting for publishers and journals', async () => {
    adapter.mockImplementation(async (config) => success(config, page(resource(config), 21)))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="next-publishers"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
    await wrapper.get('[data-test="publisher-sort"]').setValue('created_at')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 1, sort: 'created_at' })
    expect(wrapper.get('[data-test="publisher-sort"]').html()).not.toContain('created_by')

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

  it('loads and renders journal management only on the journals tab', async () => {
    adapter.mockImplementation(async (config) => success(config, page([])))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="identification-tab"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.filter(([config]) => config.url === '/journals')).toHaveLength(0)
    expect(wrapper.find('[aria-label="期刊管理"]').exists()).toBe(false)

    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.filter(([config]) => config.url === '/journals')).toHaveLength(1)
    expect(wrapper.find('[aria-label="期刊管理"]').exists()).toBe(true)
  })
  it('shows a specific empty state for every resource', async () => {
    adapter.mockImplementation(async (config) => success(config, page([])))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    expect(wrapper.text()).toContain('未找到出版商')
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未找到期刊')
  })

  it('suppresses empty states when resource loading fails', async () => {
    adapter.mockImplementation(async () => { throw new Error('offline') })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    expect(wrapper.text()).toContain('无法加载出版商')
    expect(wrapper.text()).not.toContain('未找到出版商')
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('未找到期刊')
  })

  it('creates and updates publishers with separate request models', async () => {
    adapter.mockImplementation(async (config) => success(config,
      ['post', 'patch'].includes(config.method ?? '') ? publisher : page([publisher]),
    ))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
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
    expectSaveSuccessToast()
  })

  it('does not expose the removed platform catalog', async () => {
    adapter.mockImplementation(async (config) => success(config, page([])))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()

    expect(wrapper.find('[data-test="platforms-tab"]').exists()).toBe(false)
    expect(adapter.mock.calls.some(([config]) => config.url === '/journal-platforms')).toBe(false)
  })

  it('shows Chinese journal status options and submits the selected English value', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([publisher]))
      if (config.url === '/journals' && config.method === 'get') return success(config, page([journal]))
      if (config.method === 'post') return success(config, journal)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-journal"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('添加期刊')

    const statusSelect = wrapper.get('[data-test="journal-status"]')
    expect(statusSelect.element.tagName).toBe('SELECT')
    expect(statusSelect.findAll('option').map((option) => [option.attributes('value'), option.text()])).toEqual([
      ['active', '启用'],
      ['needs_review', '待审核'],
      ['disabled', '已停用'],
    ])
    expect((statusSelect.element as HTMLSelectElement).value).toBe('active')

    await wrapper.get('[data-test="journal-name"]').setValue('New Journal')
    await wrapper.get('[data-test="journal-publisher"]').setValue('p1')
    await statusSelect.setValue('needs_review')
    await wrapper.get('[data-test="journal-platform"]').setValue('OJS')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({ status: 'needs_review', platform_code: 'OJS' })
    expectSaveSuccessToast()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('requires every journal requirement field and an HTTPS source', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([publisher]))
      if (config.url === '/journals' && config.method === 'get') return success(config, page([journal]))
      if (['post', 'patch'].includes(config.method ?? '')) return success(config, journal)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
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
    expect(wrapper.text()).toContain('每一行均须填写要求键、值、适用范围、HTTPS 来源网址和核验时间')

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

  it('preserves numeric and boolean requirement values through editing', async () => {
    const typedJournal = {
      ...journal,
      requirements: [
        { key: 'abstract_words', value: 250, scope: 'research', source_url: 'https://journal.example/guide', verified_at: '2026-11-04T00:00:00Z' },
        { key: 'anonymous', value: false, scope: 'research', source_url: 'https://journal.example/guide', verified_at: '2026-11-04T00:00:00Z' },
      ],
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([publisher]))
      if (config.url === '/journals' && config.method === 'get') return success(config, page([typedJournal]))
      if (config.method === 'patch') return success(config, typedJournal)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('否')
    expect(wrapper.text()).not.toContain('anonymous: false')
    await wrapper.get('[data-test="edit-journal-j1"]').trigger('click')
    await flushPromises()

    const valueTypes = wrapper.findAll('[data-test="requirement-type"]')
    expect(valueTypes.map((element) => (element.element as HTMLSelectElement).value)).toEqual(['number', 'boolean'])
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    const payload = JSON.parse(String(updateCall?.[0].data)) as { requirements: Array<{ value: unknown }> }
    expect(payload.requirements.map((requirement) => requirement.value)).toEqual([250, false])
    expect(typeof payload.requirements[0].value).toBe('number')
    expect(typeof payload.requirements[1].value).toBe('boolean')
  })

  it('renders unsafe API URLs as text and rejects an unsafe publisher URL', async () => {
    const unsafePublisher = { ...publisher, website_url: 'javascript:alert(1)' }
    const unsafeJournal = {
      ...journal,
      requirements: [{ key: 'abstract', value: 250, scope: 'research', source_url: 'javascript:alert(1)', verified_at: '2026-11-04T00:00:00Z' }],
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers' && config.method === 'get') return success(config, page([unsafePublisher]))
      if (config.url === '/journals') return success(config, page([unsafeJournal]))
      if (config.method === 'patch') return success(config, unsafePublisher)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('javascript:alert(1)')
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)

    await wrapper.get('[data-test="publishers-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-publisher-p1"]').trigger('click')
    await wrapper.get('[data-test="publisher-form"]').trigger('submit')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(false)
    expect(wrapper.text()).toContain('HTTPS，或经允许的本地 HTTP')
  })

  it('rejects unsafe optional journal URLs before update', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers') return success(config, page([publisher]))
      if (config.url === '/journals' && config.method === 'get') return success(config, page([journal]))
      if (config.method === 'patch') return success(config, journal)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-journal-j1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="journal-form"] input[type="url"]').setValue('javascript:alert(1)')
    await wrapper.get('[data-test="journal-form"]').trigger('submit')
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(false)
    expect(wrapper.text()).toContain('HTTPS，或经允许的本地 HTTP')
  })

  it('loads every publisher selector page and accepts a platform code', async () => {
    const publisherChoices = Array.from({ length: 101 }, (_, index) => ({ ...publisher, id: `p${index}`, name: `Publisher ${index}` }))
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals') return success(config, page([]))
      if (config.url === '/publishers' && config.params?.page_size === 20) return success(config, page([publisher]))
      if (config.url === '/publishers') {
        const pageNumber = Number(config.params?.page ?? 1)
        return success(config, { items: publisherChoices.slice((pageNumber - 1) * 100, pageNumber * 100), page: pageNumber, page_size: 100, total: 101 })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-journal"]').trigger('click')
    await flushPromises()

    expect(adapter.mock.calls.filter(([config]) => config.url === '/publishers' && config.params?.page_size === 100).map(([config]) => config.params.page)).toEqual([1, 2])
    expect(wrapper.get('[data-test="journal-publisher"]').find('option[value="p100"]').exists()).toBe(true)
    await wrapper.get('[data-test="journal-platform"]').setValue('CUSTOM_PLATFORM')
    expect((wrapper.get('[data-test="journal-platform"]').element as HTMLInputElement).value).toBe('CUSTOM_PLATFORM')
  })

  it('preserves selected journal relationships missing from selector results', async () => {
    const current = { ...journal, publisher_id: 'missing-p', platform_code: 'missing-s' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers' && config.params?.page_size === 20) return success(config, page([]))
      if (config.url === '/journals') return success(config, page([current]))
      if (config.url === '/publishers') return success(config, page([]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-journal-j1"]').trigger('click')
    await flushPromises()

    const publisherSelect = wrapper.get('[data-test="journal-publisher"]')
    const platformInput = wrapper.get('[data-test="journal-platform"]')
    expect((publisherSelect.element as HTMLSelectElement).value).toBe('missing-p')
    expect((platformInput.element as HTMLInputElement).value).toBe('missing-s')
    expect(publisherSelect.text()).toContain('missing-p')
  })

  it('keeps the delete dialog open with its error when deletion fails', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'delete') throw new Error('delete failed')
      return success(config, page([journal]))
    })
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="delete-journal-j1"]').trigger('click')
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-journal-j1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('无法删除该资源')
    expect((wrapper.get('[data-test="delete-confirm"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('requires separate soft-delete confirmation for publishers and journals', async () => {
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'delete' ? null : page(resource(config)),
    ))
    const wrapper = mount(JournalListView, { global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    await wrapper.get('[data-test="delete-publisher-p1"]').trigger('click')
    await wrapper.get('[data-test="confirm-delete-publisher-p1"]').trigger('click')
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete')).toBe(false)
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-publisher-p1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/publishers/p1')).toBe(true)

    await wrapper.get('[data-test="journals-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="delete-journal-j1"]').trigger('click')
    await wrapper.get('[data-test="delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-journal-j1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/journals/j1')).toBe(true)
  })
})
