import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import FileFamilyUpload from '../../components/FileFamilyUpload.vue'
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
const snapshot = {
  owner_author_id: 'a1', title: 'Snapshot two title', abstract: 'Snapshot abstract', keywords: ['ai'],
  article_type: 'research', language: 'en', authors: [owner, coauthor],
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

  it('displays the current version and immutable snapshots without cached coauthor secrets', async () => {
    const wrapper = mountDetail()
    await flushPromises()

    expect(wrapper.text()).toContain('Working title')
    expect(wrapper.text()).toContain('Current version: 2')
    expect(wrapper.text()).toContain('Snapshot two title')
    expect(wrapper.text()).toContain('Immutable original title')
    expect(wrapper.get('[data-test="current-files"]').text()).toContain('paper.pdf')
    expect(wrapper.get('[data-test="snapshot-history"]').find('input').exists()).toBe(false)
    for (const secret of ['private@example.invalid', 'private-phone', 'private-address', 'private-orcid', 'private-coauthor-notes', '/private/do-not-render.pdf', 'storage_path']) {
      expect(wrapper.text()).not.toContain(secret)
    }
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
    expect(wrapper.text()).toContain('Current version: 3')
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

    const download = adapter.mock.calls.find(([config]) => config.url === '/files/f1/download')
    expect(download?.[0]).toMatchObject({ method: 'get', responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:authorized-download')
  })
})
