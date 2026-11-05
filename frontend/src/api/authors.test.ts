import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import { listAuthorInstitutions, listEmails } from './authors'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: '200', headers: {}, config }
}

function pagedResponse(config: InternalAxiosRequestConfig, items: object[]) {
  const page = Number(config.params?.page ?? 1)
  return success(config, {
    items: items.slice((page - 1) * 100, page * 100),
    page,
    page_size: 100,
    total: items.length,
  })
}

describe('complete author relation fetching', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  it('fetches every email page instead of truncating at 100', async () => {
    const items = Array.from({ length: 101 }, (_, index) => ({ id: `e${index}` }))
    adapter.mockImplementation(async (config) => pagedResponse(config, items))

    const result = await listEmails('a1')

    expect(result.items).toHaveLength(101)
    expect(result.items.at(-1)?.id).toBe('e100')
    expect(adapter.mock.calls.map(([config]) => config.params.page)).toEqual([1, 2])
  })

  it('fetches every affiliation page instead of truncating at 100', async () => {
    const items = Array.from({ length: 101 }, (_, index) => ({ id: `l${index}` }))
    adapter.mockImplementation(async (config) => pagedResponse(config, items))

    const result = await listAuthorInstitutions('a1')

    expect(result.items).toHaveLength(101)
    expect(result.items.at(-1)?.id).toBe('l100')
    expect(adapter.mock.calls.map(([config]) => config.params.page)).toEqual([1, 2])
  })
})
