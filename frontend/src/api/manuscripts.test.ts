import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import {
  createManuscript,
  createManuscriptVersion,
  deleteManuscript,
  getManuscript,
  getManuscriptVersion,
  listManuscripts,
  listManuscriptVersions,
  replaceManuscriptAuthors,
  updateManuscript,
} from './manuscripts'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

describe('manuscript API', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>(async (config) => success(config, {}))
    api.defaults.adapter = adapter
  })

  it('queries the server with allowlisted pagination, status, and sorting', async () => {
    await listManuscripts({ page: 2, page_size: 10, status: 'draft', sort: 'title', order: 'asc' })

    expect(adapter.mock.calls[0][0]).toMatchObject({
      method: 'get', url: '/manuscripts',
      params: { page: 2, page_size: 10, status: 'draft', sort: 'title', order: 'asc' },
    })
  })

  it('sends create, metadata update, and soft delete to their distinct endpoints', async () => {
    const create = {
      owner_author_id: 'a1', title: 'Title', abstract: 'Abstract', keywords: ['one'],
      article_type: 'research', language: 'en',
      authors: [{ author_id: 'a1', position: 1, is_corresponding: true }],
    }
    await createManuscript(create)
    await updateManuscript('m1', { title: 'Updated', notes: null })
    await deleteManuscript('m1')
    await getManuscript('m1')

    expect(adapter.mock.calls.map(([config]) => [config.method, config.url, config.data])).toEqual([
      ['post', '/manuscripts', JSON.stringify(create)],
      ['patch', '/manuscripts/m1', JSON.stringify({ title: 'Updated', notes: null })],
      ['delete', '/manuscripts/m1', undefined],
      ['get', '/manuscripts/m1', undefined],
    ])
  })

  it('replaces authorship with ids, positions, flags, and explicit confirmation', async () => {
    const payload = {
      authors: [{ author_id: 'a1', position: 1, is_corresponding: true }],
      confirm_authorship_change: true as const,
    }
    await replaceManuscriptAuthors('m1', payload)

    expect(adapter.mock.calls[0][0]).toMatchObject({
      method: 'put', url: '/manuscripts/m1/authors', data: JSON.stringify(payload),
    })
  })

  it('creates and reads immutable manuscript versions', async () => {
    await listManuscriptVersions('m1', { page: 2, page_size: 5 })
    await createManuscriptVersion('m1', { label: 'Revision', change_note: 'Changes' })
    await getManuscriptVersion('m1', 'v2')

    expect(adapter.mock.calls.map(([config]) => [config.method, config.url, config.params, config.data])).toEqual([
      ['get', '/manuscripts/m1/versions', { page: 2, page_size: 5 }, undefined],
      ['post', '/manuscripts/m1/versions', undefined, JSON.stringify({ label: 'Revision', change_note: 'Changes' })],
      ['get', '/manuscripts/m1/versions/v2', undefined, undefined],
    ])
  })
})
