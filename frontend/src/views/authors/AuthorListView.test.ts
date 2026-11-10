import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import AuthorListView from './AuthorListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

const admin: User = {
  id: 'u1', username: 'admin', display_name: 'Admin', roles: ['system_admin'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const author = {
  id: 'a1', display_name: 'Listed Author', alternate_names: [], status: 'active',
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }
const stubs = { RouterLink: { template: '<a><slot /></a>' } }

describe('AuthorListView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().setSession(admin, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  function mountList() {
    return mount(AuthorListView, { global: { stubs } })
  }

  it('uses server pagination and allowlisted author sorting', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      items: [author], page: 1, page_size: 20, total: 42,
    }))
    const wrapper = mountList()
    await flushPromises()
    expect(wrapper.text()).toContain('Listed Author')
    const links = wrapper.findAll('a')
    expect(links.find((link) => link.text() === '查看')?.classes()).toContain('action-button--view')
    expect(links.find((link) => link.text() === '授权')?.classes()).toContain('action-button--permission')
    expect(adapter.mock.calls[0][0].params).toMatchObject({
      page: 1, page_size: 20, sort: 'display_name', order: 'asc',
    })

    await wrapper.get('[data-test="next-authors"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
    await wrapper.get('[data-test="author-sort"]').setValue('created_at')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 1, sort: 'created_at' })
    expect(wrapper.get('[data-test="author-sort"]').html()).not.toContain('created_by')
  })

  it('creates authors through the confirmed typed form', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post') return success(config, author)
      return success(config, emptyPage)
    })
    const wrapper = mountList()
    await flushPromises()
    expect(wrapper.text()).toContain('未找到作者')
    await wrapper.get('[data-test="add-author"]').trigger('click')
    await wrapper.get('[data-test="display-name"]').setValue('New Author')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('[data-test="author-create-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(createCall?.[0].url).toBe('/authors')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({
      display_name: 'New Author', confirm_identity_change: true,
    })
  })

  it('requires separate confirmation before soft-deleting an author', async () => {
    adapter.mockImplementation(async (config) => success(config,
      config.method === 'delete' ? null : { ...emptyPage, items: [author], total: 1 },
    ))
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="delete-author-a1"]').trigger('click')
    await wrapper.get('[data-test="confirm-delete-author-a1"]').trigger('click')
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete')).toBe(false)

    await wrapper.get('[data-test="author-delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-author-a1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/authors/a1')).toBe(true)
  })

  it('manages institutions from paginated summaries with confirmed soft delete', async () => {
    const institution = {
      id: 'i1', name: 'Summary Institution', institution_type: 'university',
      website_url: 'https://institution.example', country_code: 'CN', city: 'Beijing',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [institution], total: 1 })
      }
      if (config.url === '/institutions/i1' && config.method === 'get') {
        return success(config, {
          ...institution, address_line1: null, address_line2: null, region: null, postal_code: null,
          created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
        })
      }
      if (['post', 'patch', 'delete'].includes(config.method ?? '')) return success(config, institution)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Summary Institution')
    expect(wrapper.text()).not.toContain('address_line1')

    await wrapper.get('[data-test="add-institution"]').trigger('click')
    await wrapper.get('[data-test="institution-name"]').setValue('New Institution')
    await wrapper.get('[data-test="institution-website"]').setValue('https://new.example')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({
      name: 'New Institution', website_url: 'https://new.example',
    })

    await wrapper.get('[data-test="edit-institution-i1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="institution-name"]').setValue('Updated Institution')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(updateCall?.[0].url).toBe('/institutions/i1')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({ name: 'Updated Institution' })

    await wrapper.get('[data-test="delete-institution-i1"]').trigger('click')
    await wrapper.get('[data-test="institution-delete-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-institution-i1"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'delete' && config.url === '/institutions/i1')).toBe(true)
  })

  it('submits the selected country code from Chinese options', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') return success(config, emptyPage)
      if (config.method === 'post') return success(config, {})
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-institution"]').trigger('click')

    const countrySelect = wrapper.get('[data-test="institution-country"]')
    expect(countrySelect.element.tagName).toBe('SELECT')
    expect(countrySelect.get('option[value=""]').text()).toBe('未设置')
    expect(countrySelect.get('option[value="CN"]').text()).toBe('中国（CN）')
    expect(countrySelect.get('option[value="US"]').text()).toBe('美国（US）')
    await wrapper.get('[data-test="institution-name"]').setValue('New Institution')
    await countrySelect.setValue('US')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({ country_code: 'US' })
  })

  it('preserves an uncommon existing country code when editing', async () => {
    const institution = {
      id: 'i1', name: 'Brazilian Institution', institution_type: 'university',
      website_url: null, country_code: 'BR', city: 'São Paulo',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [institution], total: 1 })
      }
      if (config.url === '/institutions/i1' && config.method === 'get') {
        return success(config, {
          ...institution, address_line1: null, address_line2: null, region: null, postal_code: null,
          created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
        })
      }
      if (config.method === 'patch') return success(config, institution)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-institution-i1"]').trigger('click')
    await flushPromises()

    const countrySelect = wrapper.get('[data-test="institution-country"]')
    expect((countrySelect.element as HTMLSelectElement).value).toBe('BR')
    expect(countrySelect.get('option[value="BR"]').text()).toBe('其他（BR）')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({ country_code: 'BR' })
  })

  it('submits region and postal code when creating an institution', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') return success(config, emptyPage)
      if (config.method === 'post') return success(config, {})
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="add-institution"]').trigger('click')
    await wrapper.get('[data-test="institution-name"]').setValue('New Institution')
    await wrapper.get('[data-test="institution-region"]').setValue('Zhejiang')
    await wrapper.get('[data-test="institution-postal-code"]').setValue('310000')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({
      region: 'Zhejiang', postal_code: '310000',
    })
  })

  it('loads and updates region and postal code through institution details', async () => {
    const summary = {
      id: 'i1', name: 'Detailed Institution', institution_type: 'university',
      website_url: null, country_code: 'CN', city: 'Hangzhou',
    }
    const detail = {
      ...summary, address_line1: null, address_line2: null,
      region: 'Zhejiang', postal_code: '310000',
      created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [summary], total: 1 })
      }
      if (config.url === '/institutions/i1' && config.method === 'get') return success(config, detail)
      if (config.method === 'patch') return success(config, detail)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-institution-i1"]').trigger('click')
    await flushPromises()

    expect((wrapper.get('[data-test="institution-region"]').element as HTMLInputElement).value).toBe('Zhejiang')
    expect((wrapper.get('[data-test="institution-postal-code"]').element as HTMLInputElement).value).toBe('310000')
    await wrapper.get('[data-test="institution-region"]').setValue('New Region')
    await wrapper.get('[data-test="institution-postal-code"]').setValue('100000')
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    const updateCall = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(JSON.parse(String(updateCall?.[0].data))).toMatchObject({
      region: 'New Region', postal_code: '100000',
    })
  })

  it('does not open institution editing when details cannot load', async () => {
    const summary = {
      id: 'i1', name: 'Detailed Institution', institution_type: 'university',
      website_url: null, country_code: 'CN', city: 'Hangzhou',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') {
        return success(config, { ...emptyPage, items: [summary], total: 1 })
      }
      if (config.url === '/institutions/i1' && config.method === 'get') throw new Error('offline')
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="edit-institution-i1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="institution-form"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('无法加载单位详情')
  })

  it('renders unsafe institution URLs as text and rejects them on submit', async () => {
    const institution = {
      id: 'i1', name: 'Unsafe Institution', institution_type: null,
      website_url: 'javascript:alert(1)', country_code: null, city: null,
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, emptyPage)
      if (config.url === '/institutions' && config.method === 'get') return success(config, { ...emptyPage, items: [institution], total: 1 })
      if (config.url === '/institutions/i1' && config.method === 'get') {
        return success(config, {
          ...institution, address_line1: null, address_line2: null, region: null, postal_code: null,
          created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
        })
      }
      if (config.method === 'patch') return success(config, institution)
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('[data-test="institutions-tab"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('javascript:alert(1)')
    await wrapper.get('[data-test="edit-institution-i1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="institution-form"]').trigger('submit')
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => config.method === 'patch')).toBe(false)
    expect(wrapper.text()).toContain('HTTPS，或经允许的本地 HTTP')
  })

  it('does not show an empty state when author loading fails', async () => {
    adapter.mockImplementation(async () => { throw new Error('offline') })
    const wrapper = mountList()
    await flushPromises()

    expect(wrapper.text()).toContain('无法加载作者')
    expect(wrapper.text()).not.toContain('未找到作者')
  })
})
