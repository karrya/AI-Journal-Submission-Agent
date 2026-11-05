import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError, type AxiosAdapter, type AxiosProgressEvent, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { api } from '../api/client'
import type { ManuscriptFile } from '../api/files'
import FileFamilyUpload from './FileFamilyUpload.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 201, statusText: '201', headers: {}, config }
}

const uploadedFile: ManuscriptFile = {
  id: 'f1', file_family_id: 'family1', manuscript_id: 'm1', manuscript_version_id: 'v1',
  file_type: 'main_manuscript', display_name: 'Main manuscript', file_version: 1,
  original_filename: 'paper.pdf', mime_type: 'application/pdf', extension: '.pdf',
  size_bytes: 8, sha256: 'a'.repeat(64), scan_status: 'not_scanned',
  integrity_status: 'normal', status: 'active', created_at: '2026-11-01T00:00:00Z',
  uploaded_by: 'u1',
}

function selectFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
  const input = wrapper.get('[data-test="file-input"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  return input.trigger('change')
}

describe('FileFamilyUpload', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  it('uploads a new family with multipart metadata and Axios progress', async () => {
    let finishUpload!: () => void
    adapter.mockImplementation(async (config) => {
      config.onUploadProgress?.({ loaded: 4, total: 8, progress: 0.5 } as AxiosProgressEvent)
      return new Promise<AxiosResponse>((resolve) => {
        finishUpload = () => resolve(success(config, uploadedFile))
      })
    })
    const wrapper = mount(FileFamilyUpload, {
      props: { manuscriptId: 'm1', versionId: 'v1', currentFiles: [] },
    })
    await selectFile(wrapper, new File(['%PDF-1.4'], 'paper.pdf', { type: 'application/pdf' }))
    await wrapper.get('[data-test="file-type"]').setValue('main_manuscript')
    await wrapper.get('[data-test="display-name"]').setValue('Main manuscript')
    expect(wrapper.text()).toContain('8 字节')
    expect(wrapper.text()).toContain('服务端必须校验文件内容')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.text()).toContain('50%'))
    finishUpload()
    await flushPromises()

    expect(adapter).toHaveBeenCalledOnce()
    const config = adapter.mock.calls[0][0]
    expect(config.url).toBe('/manuscripts/m1/versions/v1/files')
    expect(config.data.get('file_type')).toBe('main_manuscript')
    expect(config.data.get('display_name')).toBe('Main manuscript')
    expect(config.data.get('file_family_id')).toBeNull()
    expect(wrapper.text()).toContain('100%')
    expect(wrapper.emitted('uploaded')?.[0]?.[0]).toEqual(uploadedFile)
  })

  it('uploads to an existing family without editable family metadata', async () => {
    adapter.mockImplementation(async (config) => success(config, { ...uploadedFile, file_version: 2 }))
    const wrapper = mount(FileFamilyUpload, {
      props: { manuscriptId: 'm1', versionId: 'v1', currentFiles: [uploadedFile] },
    })
    await wrapper.get('[data-test="existing-family-mode"]').setValue(true)
    await wrapper.get('[data-test="file-family"]').setValue('family1')
    await selectFile(wrapper, new File(['%PDF-1.4'], 'revision.pdf', { type: 'application/pdf' }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const data = adapter.mock.calls[0][0].data
    expect(data.get('file_family_id')).toBe('family1')
    expect(data.get('file_type')).toBeNull()
    expect(data.get('display_name')).toBeNull()
    expect(wrapper.find('[data-test="file-type"]').exists()).toBe(false)
  })

  it('shows refresh guidance for a current-version conflict without retrying', async () => {
    adapter.mockImplementation(async (config) => {
      throw new AxiosError('Conflict', '409', config, undefined, {
        data: { code: 'INVALID_MANUSCRIPT_STATE', message: 'not current' },
        status: 409, statusText: 'Conflict', headers: {}, config,
      })
    })
    const wrapper = mount(FileFamilyUpload, {
      props: { manuscriptId: 'm1', versionId: 'v1', currentFiles: [] },
    })
    await wrapper.get('[data-test="file-type"]').setValue('main_manuscript')
    await wrapper.get('[data-test="display-name"]').setValue('Main manuscript')
    await selectFile(wrapper, new File(['%PDF-1.4'], 'paper.pdf', { type: 'application/pdf' }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(adapter).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('请先刷新当前稿件版本再重新上传')
    await wrapper.get('[data-test="refresh-version"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(adapter).toHaveBeenCalledOnce()
  })

  it('never renders storage paths returned by an unsafe response', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      ...uploadedFile, storage_path: '/private/storage/paper.pdf',
    }))
    const wrapper = mount(FileFamilyUpload, {
      props: { manuscriptId: 'm1', versionId: 'v1', currentFiles: [] },
    })
    await wrapper.get('[data-test="file-type"]').setValue('main_manuscript')
    await wrapper.get('[data-test="display-name"]').setValue('Main manuscript')
    await selectFile(wrapper, new File(['%PDF-1.4'], 'paper.pdf', { type: 'application/pdf' }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).not.toContain('/private/storage/paper.pdf')
    expect(wrapper.text()).not.toContain('storage_path')
  })
})
