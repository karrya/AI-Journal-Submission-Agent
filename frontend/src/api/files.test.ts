import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import { deleteFile, downloadFile, getFile, listFiles } from './files'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

describe('file API', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>(async (config) => success(config, {}))
    api.defaults.adapter = adapter
  })

  it('lists current-version files with server pagination', async () => {
    await listFiles('m1', 'v1', { page: 2, page_size: 10 })

    expect(adapter.mock.calls[0][0]).toMatchObject({
      method: 'get', url: '/manuscripts/m1/versions/v1/files',
      params: { page: 2, page_size: 10 },
    })
  })

  it('reads metadata and soft-deletes through file resource endpoints', async () => {
    await getFile('f1')
    await deleteFile('f1')

    expect(adapter.mock.calls.map(([config]) => [config.method, config.url])).toEqual([
      ['get', '/files/f1'], ['delete', '/files/f1'],
    ])
  })

  it('downloads a blob only from the authorized download endpoint', async () => {
    await downloadFile('f1')

    expect(adapter.mock.calls[0][0]).toMatchObject({
      method: 'get', url: '/files/f1/download', responseType: 'blob',
    })
  })
})
