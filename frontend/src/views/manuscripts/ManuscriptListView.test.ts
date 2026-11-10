import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import ManuscriptListView from './ManuscriptListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

const operator: User = {
  id: 'u1', username: 'operator', display_name: 'Operator', roles: ['submission_operator'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const owner = {
  id: 'a1', display_name: 'Owner One', alternate_names: [], status: 'active',
  orcid: 'private-owner-orcid', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const manuscript = {
  id: 'm1', internal_number: 'MS-1', owner_author_id: 'a1', title: 'Visible manuscript',
  abstract: 'Abstract', keywords: ['ai'], article_type: 'research', language: 'en',
  status: 'draft', current_version_id: 'v1',
  authors: [{ author_id: 'a1', display_name: 'Owner One', position: 1, is_corresponding: true }],
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }
const stubs = { RouterLink: { template: '<a><slot /></a>' } }

describe('ManuscriptListView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().setSession(operator, 'csrf')
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  it('uses server pagination and allowlisted filters without exposing sensitive author fields', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      items: [{ ...manuscript, authors: [{ ...manuscript.authors[0], notes: 'private-coauthor-notes' }] }],
      page: 1, page_size: 20, total: 21,
    }))
    const wrapper = mount(ManuscriptListView, { global: { stubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('Visible manuscript')
    const workspaceLink = wrapper.findAll('a').find((link) => link.text() === '打开工作区')
    expect(workspaceLink?.classes()).toContain('action-button--view')
    expect(wrapper.get('[data-test="apply-filters"]').classes()).toContain('action-button--neutral')
    expect(wrapper.text()).not.toContain('private-coauthor-notes')
    expect(wrapper.text()).not.toContain('private-owner-orcid')
    expect(adapter.mock.calls[0][0].params).toMatchObject({ sort: 'created_at', order: 'desc' })
    await wrapper.get('[data-test="status-filter"]').setValue('draft')
    await wrapper.get('[data-test="apply-filters"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ status: 'draft', page: 1 })
    await wrapper.get('[data-test="next-manuscripts"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params).toMatchObject({ page: 2 })
  })

  it('creates a manuscript with selected owner, metadata, and minimal confirmed authorship', async () => {
    const extendedMetadata = {
      funding_number: 'FUND-2026-001',
      funding_name: 'National Research Foundation',
      publication_statement: 'Publication statement',
      acknowledgements: 'Acknowledgements',
      author_contributions: 'Author contributions',
      clinical_trial_number: 'NCT20260001',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/authors') return success(config, { ...emptyPage, items: [owner], total: 1 })
      if (config.method === 'post') return success(config, manuscript, 201)
      return success(config, emptyPage)
    })
    const wrapper = mount(ManuscriptListView, { global: { stubs } })
    await flushPromises()
    await wrapper.get('[data-test="add-manuscript"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="owner-author"]').setValue('a1')
    await wrapper.get('[data-test="title"]').setValue('New manuscript')
    await wrapper.get('[data-test="abstract"]').setValue('A complete abstract')
    await wrapper.get('[data-test="keywords"]').setValue('ai, methods')
    await wrapper.get('[data-test="article-type"]').setValue('research')
    const languageSelect = wrapper.get('[data-test="language"]')
    expect(languageSelect.element.tagName).toBe('SELECT')
    expect(languageSelect.findAll('option').map((option) => [option.attributes('value'), option.text()])).toEqual([
      ['en', '英语'],
      ['zh', '中文'],
    ])
    await languageSelect.setValue('zh')
    for (const [field, value] of Object.entries(extendedMetadata)) {
      await wrapper.get(`[data-test="${field.replace(/_/g, '-')}"]`).setValue(value)
    }
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('[data-test="create-authorship-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post')
    expect(createCall?.[0].url).toBe('/manuscripts')
    const payload = JSON.parse(String(createCall?.[0].data))
    expect(payload).toMatchObject({
      owner_author_id: 'a1', title: 'New manuscript', abstract: 'A complete abstract',
      keywords: ['ai', 'methods'], article_type: 'research', language: 'zh',
      ...extendedMetadata,
    })
    expect(payload.authors).toEqual([{ author_id: 'a1', position: 1, is_corresponding: true }])
    expect(JSON.stringify(payload)).not.toContain('display_name')
    expect(JSON.stringify(payload)).not.toContain('private-owner-orcid')
  })

  it('does not show an empty state when manuscript loading fails', async () => {
    adapter.mockRejectedValue(new Error('offline'))
    const wrapper = mount(ManuscriptListView, { global: { stubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('无法加载稿件')
    expect(wrapper.text()).not.toContain('未找到稿件')
  })
})
