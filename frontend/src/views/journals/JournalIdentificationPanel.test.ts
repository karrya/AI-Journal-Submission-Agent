import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from '../../api/client'
import { expectSaveSuccessToast } from '../../test/toast'
import JournalIdentificationPanel from './JournalIdentificationPanel.vue'

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

const candidateOne = {
  id: 'j1', name: 'Journal of Science', publisher_id: 'p1', publisher_name: 'Publisher One',
  issn: null, eissn: null, website_url: null, identity_status: 'NEEDS_CONFIRMATION',
  match_reasons: ['名称精确匹配'], conflict_reason: null,
  updated_at: '2026-11-17T00:00:00Z', verified_at: null,
}
const candidateTwo = {
  ...candidateOne, id: 'j2', publisher_id: 'p2', publisher_name: 'Publisher Two',
  website_url: 'https://example.com',
}
const identifyResponse = {
  task_id: 'task1', status: 'SUCCEEDED', candidates: [candidateOne, candidateTwo],
}
const verifiedCandidate = {
  ...candidateTwo, identity_status: 'VERIFIED', verified_at: '2026-11-17T01:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }

describe('JournalIdentificationPanel', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows candidates and requires manual selection before confirmation', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') return success(config, identifyResponse)
      if (config.url?.endsWith('/confirm-identity')) return success(config, verifiedCandidate)
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal of Science')
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('[data-test="identity-candidate"]').length).toBe(2)
    expect(wrapper.find('a[href="https://example.com"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="select-candidate-j2"]').setValue(true)
    await wrapper.get('[data-test="confirm-identity"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已验证')
    expectSaveSuccessToast()
  })

  it('shows a validation error for invalid ISSN without showing candidates', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return Promise.reject({
          response: { status: 422, data: { code: 'VALIDATION_ERROR', message: 'ISSN（国际标准连续出版物号）校验位无效' } },        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Bad ISSN')
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher')
    await wrapper.get('[data-test="identify-issn"]').setValue('00000000')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('ISSN（国际标准连续出版物号）校验位无效')
    expect(wrapper.findAll('[data-test="identity-candidate"]').length).toBe(0)
  })

  it('links publisher and journal options and autofills identifiers', async () => {
    vi.useFakeTimers()
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options') {
        return success(config, { items: [{ id: 'p1', name: 'Publisher One' }] })
      }
      if (config.url === '/journals/options') {
        return success(config, {
          items: [{
            id: 'j1', publisher_id: 'p1', name: 'Journal One', issn: '03785955',
            eissn: '18781128', website_url: 'https://journal.example',
          }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    const publisherInput = wrapper.get('[data-test="identify-publisher-name"]')
    expect(publisherInput.attributes('list')).toBe('publisher-options')
    await publisherInput.setValue('Publisher One')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect(adapter.mock.calls.some(([config]) => (
      config.url === '/journals/options' && config.params?.publisher_id === 'p1'
    ))).toBe(true)

    const journalInput = wrapper.get('[data-test="identify-journal-name"]')
    expect(journalInput.attributes('list')).toBe('journal-options')
    await journalInput.setValue('Journal One')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).toBe('03785955')
    expect((wrapper.get('[data-test="identify-eissn"]').element as HTMLInputElement).value).toBe('18781128')
    expect((wrapper.get('[data-test="identify-website"]').element as HTMLInputElement).value).toBe('https://journal.example')

    await publisherInput.setValue('Publisher Two')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect((journalInput.element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('[data-test="identify-eissn"]').element as HTMLInputElement).value).toBe('')
  })
  it('autofills a journal entered before publisher options finish loading', async () => {
    vi.useFakeTimers()
    let finishPublisherOptions: (() => void) | undefined
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options' && config.params?.name === 'Publisher One') {
        return new Promise<AxiosResponse>((resolve) => {
          finishPublisherOptions = () => resolve(success(config, {
            items: [{ id: 'p1', name: 'Publisher One' }],
          }))
        })
      }
      if (config.url === '/journals/options') {
        return success(config, {
          items: [{
            id: 'j1', publisher_id: 'p1', name: 'Journal One', issn: '03785955',
            eissn: '18781128', website_url: 'https://journal.example',
          }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher One')
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal One')
    await vi.advanceTimersByTimeAsync(250)
    expect(finishPublisherOptions).toBeDefined()
    finishPublisherOptions?.()
    await flushPromises()

    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).toBe('03785955')
    expect((wrapper.get('[data-test="identify-eissn"]').element as HTMLInputElement).value).toBe('18781128')
    expect((wrapper.get('[data-test="identify-website"]').element as HTMLInputElement).value).toBe('https://journal.example')
  })

  it('clears identification state and ignores stale option responses', async () => {
    vi.useFakeTimers()
    let finishStaleOptions: (() => void) | undefined
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options' && config.params?.name === 'Stale Publisher') {
        return new Promise<AxiosResponse>((resolve) => {
          finishStaleOptions = () => resolve(success(config, {
            items: [{ id: 'stale-publisher', name: 'Stale Publisher' }],
          }))
        })
      }
      if (config.url === '/publishers/options') {
        return success(config, { items: [{ id: 'p1', name: 'Publisher One' }] })
      }
      if (config.url === '/journals/options') {
        return success(config, {
          items: [{
            id: 'j1', publisher_id: 'p1', name: 'Journal One', issn: '03785955',
            eissn: '18781128', website_url: 'https://journal.example',
          }],
        })
      }
      if (config.url === '/journals/identify') return success(config, identifyResponse)
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    const publisherInput = wrapper.get('[data-test="identify-publisher-name"]')
    await publisherInput.setValue('Publisher One')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal One')
    await wrapper.get('input[maxlength="100"]').setValue('Review')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('textarea').setValue('confirmation note')
    expect(wrapper.findAll('[data-test="identity-candidate"]')).not.toHaveLength(0)
    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).not.toBe('')

    await wrapper.get('[data-test="clear-identification"]').trigger('click')
    await flushPromises()
    const inputSelectors = [
      'identify-publisher-name',
      'identify-journal-name',
      'identify-issn',
      'identify-eissn',
      'identify-website',
    ]
    for (const selector of inputSelectors) {
      expect((wrapper.get(`[data-test="${selector}"]`).element as HTMLInputElement).value).toBe('')
    }
    expect((wrapper.get('input[maxlength="100"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.findAll('[data-test="identity-candidate"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('识别任务状态：')
    expect(wrapper.find('textarea').exists()).toBe(false)

    await publisherInput.setValue('Stale Publisher')
    await vi.advanceTimersByTimeAsync(250)
    expect(finishStaleOptions).toBeDefined()
    await wrapper.get('[data-test="clear-identification"]').trigger('click')
    await flushPromises()
    finishStaleOptions?.()
    await flushPromises()
    expect((publisherInput.element as HTMLInputElement).value).toBe('')
    expect(adapter.mock.calls.some(([config]) => (
      config.url === '/journals/options' && config.params?.publisher_id === 'stale-publisher'
    ))).toBe(false)
  })

  it('does not confirm conflict candidates', async () => {
    const conflict = {
      ...candidateOne, identity_status: 'CONFLICT', conflict_reason: '标识冲突',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-conflict', status: 'SUCCEEDED', candidates: [conflict] })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Conflict Journal')
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('标识冲突')
    expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
    expect(adapter.mock.calls.filter(([config]) => config.method === 'post')).toHaveLength(1)
  })
})
