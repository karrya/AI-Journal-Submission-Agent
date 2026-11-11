import { readFileSync } from 'node:fs'
import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { expectSaveSuccessToast } from '../../test/toast'
import { useAuthStore, type User } from '../../stores/auth'
import FileFamilyUpload from '../../components/FileFamilyUpload.vue'
import AuthorshipEditor from '../../components/AuthorshipEditor.vue'
import ManuscriptDetailView from './ManuscriptDetailView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

const operator: User = {
  id: 'u1', username: 'operator', display_name: 'Operator', roles: ['submission_operator'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const owner = { author_id: 'a1', display_name: 'Owner One', position: 1, is_corresponding: true }
const coauthor = { author_id: 'b1', display_name: 'Coauthor B', position: 2, is_corresponding: false }
const extendedMetadata = {
  funding_number: 'FUND-2026-001',
  funding_name: 'National Research Foundation',
  publication_statement: 'Publication statement',
  acknowledgements: 'Acknowledgements',
  author_contributions: 'Author contributions',
  clinical_trial_number: 'NCT20260001',
}
const snapshot = {
  owner_author_id: 'a1', title: 'Snapshot two title', abstract: 'Snapshot abstract', keywords: ['ai'],
  article_type: 'research', language: 'zh', ...extendedMetadata, authors: [owner, coauthor],
}
const versions = [
  {
    id: 'v2', manuscript_id: 'm1', version_number: 2, label: 'Current label',
    metadata_snapshot: snapshot, created_at: '2026-11-02T00:00:00Z', created_by: 'u1',
  },
  {
    id: 'v1', manuscript_id: 'm1', version_number: 1, label: 'Original',
    metadata_snapshot: { ...snapshot, title: 'Immutable original title' },
    created_at: '2026-11-01T00:00:00Z', created_by: 'u1',
  },
]
const manuscript = {
  id: 'm1', internal_number: 'MS-1', owner_author_id: 'a1', title: 'Working title',
  abstract: 'Working abstract', keywords: ['ai'], article_type: 'research', language: 'en',
  status: 'draft', current_version_id: 'v2', authors: [owner, coauthor],
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-02T00:00:00Z',
}
const file = {
  id: 'f1', file_family_id: 'family1', manuscript_id: 'm1', manuscript_version_id: 'v2',
  file_type: 'main_manuscript', display_name: 'Main manuscript', file_version: 2,
  original_filename: 'paper.pdf', mime_type: 'application/pdf', extension: '.pdf', size_bytes: 8,
  sha256: 'a'.repeat(64), scan_status: 'not_scanned', integrity_status: 'normal', status: 'active',
  created_at: '2026-11-02T00:00:00Z', uploaded_by: 'u1', storage_path: '/private/do-not-render.pdf',
}
const authorOptions = [
  { id: 'a1', display_name: 'Owner One', alternate_names: [], status: 'active', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
  {
    id: 'b1', display_name: 'Coauthor B', alternate_names: [], status: 'active',
    email: 'private@example.invalid', phone_number: 'private-phone', address_line1: 'private-address',
    orcid: 'private-orcid', notes: 'private-coauthor-notes',
    created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
  },
]

describe('ManuscriptDetailView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().setSession(operator, 'csrf')
    adapter = vi.fn<AxiosAdapter>(async (config) => {
      if (config.url === '/manuscripts/m1') return success(config, manuscript)
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: versions, page: 1, page_size: 20, total: 2 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    api.defaults.adapter = adapter
  })

  afterEach(() => vi.restoreAllMocks())

  function mountDetail() {
    return mount(ManuscriptDetailView, {
      props: { manuscriptId: 'm1' },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
  }

  it('renders stored snapshot positions without a second ordered-list marker', async () => {
    const wrapper = mountDetail()
    await flushPromises()

    const authorship = wrapper.get('[data-test="snapshot-authorship"]')
    expect(authorship.findAll('li').map((item) => item.text())).toEqual([
      '1. Owner One · 通讯作者',
      '2. Coauthor B',
    ])
    expect(authorship.classes()).toContain('authorship-position-list')
    const stylesheet = readFileSync('src/style.css', 'utf8')
    expect(stylesheet).toMatch(/\.authorship-position-list\s*\{[^}]*list-style:\s*none;/s)
  })

  it('defensively hides cached coauthor secrets and unexpected storage paths', async () => {
    const wrapper = mountDetail()
    await flushPromises()

    expect(wrapper.text()).toContain('Working title')
    expect(wrapper.text()).toContain('当前版本：2')
    expect(wrapper.text()).toContain('Snapshot two title')
    expect(wrapper.text()).toContain('Immutable original title')
    expect(wrapper.get('[data-test="current-files"]').text()).toContain('paper.pdf')
    expect(wrapper.findAll('a').find((link) => link.text() === '返回稿件列表')?.classes()).toContain('action-button--neutral')
    expect(wrapper.get('[data-test="download-f1"]').classes()).toContain('action-button--download')
    expect(wrapper.get('[data-test="snapshot-history"]').find('input').exists()).toBe(false)
    for (const secret of ['private@example.invalid', 'private-phone', 'private-address', 'private-orcid', 'private-coauthor-notes', '/private/do-not-render.pdf', 'storage_path']) {
      expect(wrapper.text()).not.toContain(secret)
    }
  })

  it('WEB-01 keeps coauthor secrets out of the UI and manuscript Network payloads', async () => {
    const safeFile: Record<string, unknown> = { ...file }
    delete safeFile.storage_path
    const responses: unknown[] = []
    adapter.mockImplementation(async (config) => {
      let data: unknown
      if (config.url === '/manuscripts/m1') data = manuscript
      else if (config.url === '/manuscripts/m1/versions') data = { items: versions, page: 1, page_size: 20, total: 2 }
      else if (config.url === '/manuscripts/m1/versions/v2') data = versions[0]
      else if (config.url === '/manuscripts/m1/versions/v2/files') data = { items: [safeFile], page: 1, page_size: 100, total: 1 }
      else if (config.url === '/authors') data = { items: authorOptions, page: 1, page_size: 100, total: 2 }
      else throw new Error(`Unexpected request: ${config.method} ${config.url}`)
      if (config.url !== '/authors') responses.push(data)
      return success(config, data)
    })
    const wrapper = mountDetail()
    await flushPromises()

    expect(wrapper.text()).toContain('Working title')
    expect(responses).toHaveLength(4)
    for (const payload of responses) {
      const serialized = JSON.stringify(payload)
      for (const forbidden of ['email', 'phone_number', 'address_line1', 'orcid', 'notes', 'storage_path', 'stored_filename']) {
        expect(serialized).not.toContain(forbidden)
      }
      expect(wrapper.text()).not.toContain('private-coauthor-notes')
    }
  })

  it('renders localized language and extended metadata in immutable snapshots', async () => {
    const wrapper = mountDetail()
    await flushPromises()

    const history = wrapper.get('[data-test="snapshot-history"]').text()
    expect(history).toContain('中文')
    for (const value of Object.values(extendedMetadata)) expect(history).toContain(value)
  })

  it('updates language and extended metadata through the working form', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'patch') {
        return success(config, { ...manuscript, language: 'zh', ...extendedMetadata })
      }
      if (config.url === '/manuscripts/m1') return success(config, manuscript)
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: versions, page: 1, page_size: 20, total: 2 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    const languageSelect = wrapper.get('[data-test="metadata-language"]')
    expect(languageSelect.element.tagName).toBe('SELECT')
    expect(languageSelect.findAll('option').map((option) => [option.attributes('value'), option.text()])).toEqual([
      ['en', '英语'],
      ['zh', '中文'],
    ])
    await languageSelect.setValue('zh')
    for (const [field, value] of Object.entries(extendedMetadata)) {
      await wrapper.get(`[data-test="metadata-${field.replace(/_/g, '-')}"]`).setValue(value)
    }
    await wrapper.get('[data-test="metadata-form"]').trigger('submit')
    await flushPromises()

    const patch = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(JSON.parse(String(patch?.[0].data))).toMatchObject({
      language: 'zh', ...extendedMetadata,
    })
    expectSaveSuccessToast()
  })

  it('updates working metadata without rewriting an immutable snapshot', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'patch') return success(config, { ...manuscript, title: 'Updated working title' })
      if (config.url === '/manuscripts/m1') return success(config, manuscript)
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: versions, page: 1, page_size: 20, total: 2 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="metadata-title"]').setValue('Updated working title')
    await wrapper.get('[data-test="metadata-form"]').trigger('submit')
    await flushPromises()

    const patch = adapter.mock.calls.find(([config]) => config.method === 'patch')
    expect(JSON.parse(String(patch?.[0].data)).title).toBe('Updated working title')
    expect(wrapper.get('[data-test="snapshot-history"]').text()).toContain('Snapshot two title')
    expect(wrapper.get('[data-test="snapshot-history"]').text()).toContain('Immutable original title')
  })

  it('reloads on m1 to m2 route reuse without submitting stale authorship to m2', async () => {
    const secondOwner = { author_id: 'a2', display_name: 'Owner Two', position: 1, is_corresponding: true }
    const secondManuscript = {
      ...manuscript,
      id: 'm2', internal_number: 'MS-2', owner_author_id: 'a2', title: 'Second working title',
      current_version_id: null, authors: [secondOwner],
    }
    const secondAuthorOption = {
      ...authorOptions[0], id: 'a2', display_name: 'Owner Two',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/manuscripts/m1') return success(config, manuscript)
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: versions, page: 1, page_size: 100, total: 2 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/manuscripts/m2') return success(config, secondManuscript)
      if (config.url === '/manuscripts/m2/versions') return success(config, { items: [], page: 1, page_size: 100, total: 0 })
      if (config.url === '/authors') return success(config, { items: [...authorOptions, secondAuthorOption], page: 1, page_size: 100, total: 3 })
      if (config.method === 'put') return success(config, [secondOwner])
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    const staleEditor = wrapper.findComponent(AuthorshipEditor)

    await wrapper.setProps({ manuscriptId: 'm2' })
    staleEditor.vm.$emit('submit', {
      authors: [owner, coauthor].map(({ author_id, position, is_corresponding }) => ({ author_id, position, is_corresponding })),
      confirm_authorship_change: true,
    })
    await flushPromises()

    expect(adapter.mock.calls.filter(([config]) => config.method === 'put')).toHaveLength(0)
    expect(adapter.mock.calls.some(([config]) => config.method === 'get' && config.url === '/manuscripts/m2')).toBe(true)
    expect(wrapper.get('h1').text()).toBe('Second working title')
    expect(wrapper.text()).not.toContain('Working abstract')
    expect(wrapper.get('[data-test="snapshot-history"]').text()).not.toContain('Snapshot two title')
    expect(wrapper.get('[data-test="current-files"]').text()).not.toContain('paper.pdf')
  })

  it('replaces authorship with ids, positions, flags, and confirmation only', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'put') return success(config, [coauthor, owner])
      if (config.url === '/manuscripts/m1') return success(config, manuscript)
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: versions, page: 1, page_size: 20, total: 2 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('[data-test="authorship-form"]').trigger('submit')
    await flushPromises()

    const put = adapter.mock.calls.find(([config]) => config.method === 'put')
    expect(put?.[0].url).toBe('/manuscripts/m1/authors')
    expect(JSON.parse(String(put?.[0].data))).toEqual({
      authors: [owner, coauthor].map(({ author_id, position, is_corresponding }) => ({ author_id, position, is_corresponding })),
      confirm_authorship_change: true,
    })
    expectSaveSuccessToast()
  })

  it('refreshes both the current version and file families after upload', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    adapter.mockClear()

    wrapper.findComponent(FileFamilyUpload).vm.$emit('uploaded', file)
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => config.method === 'get' && config.url === '/manuscripts/m1')).toBe(true)
    expect(adapter.mock.calls.some(([config]) => config.url === '/manuscripts/m1/versions/v2')).toBe(true)
    expect(adapter.mock.calls.some(([config]) => config.url === '/manuscripts/m1/versions/v2/files')).toBe(true)
  })

  it('creates a new immutable version and refreshes its current files', async () => {
    const third = { ...versions[0], id: 'v3', version_number: 3, label: 'Revision three' }
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post') return success(config, third, 201)
      if (config.url === '/manuscripts/m1') return success(config, { ...manuscript, current_version_id: 'v3' })
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: [third, ...versions], page: 1, page_size: 20, total: 3 })
      if (config.url === '/manuscripts/m1/versions/v3') return success(config, third)
      if (config.url === '/manuscripts/m1/versions/v3/files') return success(config, { items: [], page: 1, page_size: 100, total: 0 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="version-label"]').setValue('Revision three')
    await wrapper.get('[data-test="version-form"]').trigger('submit')
    await flushPromises()

    expect(JSON.parse(String(adapter.mock.calls.find(([config]) => config.method === 'post')?.[0].data))).toMatchObject({ label: 'Revision three' })
    expect(wrapper.text()).toContain('当前版本：3')
    expect(adapter.mock.calls.some(([config]) => config.url === '/manuscripts/m1/versions/v3/files')).toBe(true)
  })

  it('invalidates a pending metadata edit when an upload refreshes the workspace', async () => {
    const baseAdapter = adapter.getMockImplementation()!
    let finishPatch!: (config: InternalAxiosRequestConfig) => void
    adapter.mockImplementation(async (config) => {
      if (config.method === 'patch') {
        return new Promise<AxiosResponse>((resolve) => {
          finishPatch = () => resolve(success(config, { ...manuscript, title: 'Stale response title' }))
        })
      }
      return baseAdapter(config)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="metadata-title"]').setValue('Pending title')
    await wrapper.get('[data-test="metadata-form"]').trigger('submit')

    wrapper.findComponent(FileFamilyUpload).vm.$emit('uploaded', file)
    await flushPromises()
    expect(wrapper.get('[data-test="metadata-form"] button[type="submit"]').attributes('disabled')).toBeUndefined()

    finishPatch(adapter.mock.calls.find(([config]) => config.method === 'patch')![0])
    await flushPromises()
    expect((wrapper.get('[data-test="metadata-title"]').element as HTMLInputElement).value).toBe('Working title')
  })

  it('fetches every immutable snapshot page', async () => {
    const baseAdapter = adapter.getMockImplementation()!
    const firstPage = Array.from({ length: 100 }, (_, index) => index === 0 ? versions[0] : {
      ...versions[1], id: `old-${index}`, version_number: index + 1,
      metadata_snapshot: { ...snapshot, title: `Old snapshot ${index}` },
    })
    const last = {
      ...versions[1], id: 'old-101', version_number: 101,
      metadata_snapshot: { ...snapshot, title: 'Version 101 immutable title' },
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/manuscripts/m1/versions') {
        const page = Number(config.params?.page ?? 1)
        return success(config, {
          items: page === 1 ? firstPage : [last], page, page_size: 100, total: 101,
        })
      }
      return baseAdapter(config)
    })
    const wrapper = mountDetail()
    await flushPromises()

    const pages = adapter.mock.calls.filter(([config]) => config.url === '/manuscripts/m1/versions').map(([config]) => config.params.page)
    expect(pages).toEqual([1, 2])
    expect(wrapper.get('[data-test="snapshot-history"]').text()).toContain('Version 101 immutable title')
  })

  it('does not restore stale authorship when metadata finishes after authorship', async () => {
    const baseAdapter = adapter.getMockImplementation()!
    let finishPatch!: () => void
    let finishAuthorship!: () => void
    adapter.mockImplementation(async (config) => {
      if (config.method === 'patch') {
        return new Promise<AxiosResponse>((resolve) => {
          finishPatch = () => resolve(success(config, { ...manuscript, title: 'Updated working title' }))
        })
      }
      if (config.method === 'put') {
        return new Promise<AxiosResponse>((resolve) => {
          finishAuthorship = () => resolve(success(config, [owner]))
        })
      }
      return baseAdapter(config)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="metadata-title"]').setValue('Updated working title')
    await wrapper.get('[data-test="metadata-form"]').trigger('submit')
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('[data-test="authorship-form"]').trigger('submit')

    finishAuthorship()
    await flushPromises()
    expect(wrapper.get('.authorship-list').text()).not.toContain('Coauthor B')
    finishPatch()
    await flushPromises()

    expect(wrapper.get('.authorship-list').text()).not.toContain('Coauthor B')
    expect(wrapper.get('h1').text()).toBe('Updated working title')
  })

  it('keeps version creation locked when a refresh supersedes it', async () => {
    const third = { ...versions[0], id: 'v3', version_number: 3, label: 'Revision three' }
    let refreshed = false
    let created = false
    let finishCreate!: () => void
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post') {
        if (!finishCreate) {
          return new Promise<AxiosResponse>((resolve) => {
            finishCreate = () => {
              created = true
              resolve(success(config, third, 201))
            }
          })
        }
        return success(config, third, 201)
      }
      if (config.url === '/manuscripts/m1') {
        return success(config, { ...manuscript, current_version_id: refreshed || created ? 'v3' : 'v2' })
      }
      if (config.url === '/manuscripts/m1/versions') {
        return success(config, {
          items: refreshed || created ? [third, ...versions] : versions,
          page: 1, page_size: 100, total: refreshed || created ? 3 : 2,
        })
      }
      if (config.url === '/manuscripts/m1/versions/v3') return success(config, third)
      if (config.url === '/manuscripts/m1/versions/v3/files') return success(config, { items: [], page: 1, page_size: 100, total: 0 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="version-form"]').trigger('submit')

    refreshed = true
    wrapper.findComponent(FileFamilyUpload).vm.$emit('uploaded', file)
    await flushPromises()
    await wrapper.get('[data-test="version-form"]').trigger('submit')
    finishCreate()
    await flushPromises()

    expect(adapter.mock.calls.filter(([config]) => config.method === 'post')).toHaveLength(1)
    expect(wrapper.text()).toContain('当前版本：3')
    expect(wrapper.get('[data-test="version-form"] button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('clears loading when a refresh supersedes a full workspace load', async () => {
    const third = { ...versions[0], id: 'v3', version_number: 3, label: 'Revision three' }
    let created = false
    let holdNextLoad = false
    let finishStaleLoad!: () => void
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post') {
        created = true
        holdNextLoad = true
        return success(config, third, 201)
      }
      if (config.url === '/manuscripts/m1') {
        if (holdNextLoad) {
          holdNextLoad = false
          return new Promise<AxiosResponse>((resolve) => {
            finishStaleLoad = () => resolve(success(config, { ...manuscript, current_version_id: 'v3' }))
          })
        }
        return success(config, { ...manuscript, current_version_id: created ? 'v3' : 'v2' })
      }
      if (config.url === '/manuscripts/m1/versions') return success(config, { items: created ? [third, ...versions] : versions, page: 1, page_size: 100, total: created ? 3 : 2 })
      if (config.url === '/manuscripts/m1/versions/v3') return success(config, third)
      if (config.url === '/manuscripts/m1/versions/v3/files') return success(config, { items: [], page: 1, page_size: 100, total: 0 })
      if (config.url === '/manuscripts/m1/versions/v2') return success(config, versions[0])
      if (config.url === '/manuscripts/m1/versions/v2/files') return success(config, { items: [file], page: 1, page_size: 100, total: 1 })
      if (config.url === '/authors') return success(config, { items: authorOptions, page: 1, page_size: 100, total: 2 })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.get('[data-test="version-form"]').trigger('submit')
    await flushPromises()

    wrapper.findComponent(FileFamilyUpload).vm.$emit('uploaded', file)
    finishStaleLoad()
    await flushPromises()

    expect(wrapper.text()).not.toContain('正在加载稿件工作区…')
  })

  it('revokes Blob URLs and removes anchors after a DOM click exception', async () => {
    const createObjectURL = vi.fn(() => 'blob:failed-click')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('DOM click blocked')
    })
    const wrapper = mountDetail()
    await flushPromises()
    adapter.mockImplementationOnce(async (config) => success(config, new Blob(['authorized content'])))
    await wrapper.get('[data-test="download-f1"]').trigger('click')
    await flushPromises()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('无法下载文件')
    expect(document.querySelectorAll('a[download="paper.pdf"]')).toHaveLength(0)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:failed-click')
  })

  it('downloads through the authorized endpoint rather than a storage path', async () => {
    const createObjectURL = vi.fn(() => 'blob:authorized-download')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = mountDetail()
    await flushPromises()
    adapter.mockImplementationOnce(async (config) => success(config, new Blob(['authorized content'])))
    await wrapper.get('[data-test="download-f1"]').trigger('click')
    await flushPromises()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))

    const download = adapter.mock.calls.find(([config]) => config.url === '/files/f1/download')
    expect(download?.[0]).toMatchObject({ method: 'get', responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:authorized-download')
  })
})
