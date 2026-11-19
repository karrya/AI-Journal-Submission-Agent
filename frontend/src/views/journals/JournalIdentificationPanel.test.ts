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
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('__manual_publisher__')
    const publisherInput = wrapper.get('input[data-test="identify-publisher-name"]')
    await publisherInput.setValue('Publisher')
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
    await wrapper.get('[data-test="select-candidate-j1"]').setValue(true)
    expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
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
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('__manual_publisher__')
    const publisherInput = wrapper.get('input[data-test="identify-publisher-name"]')
    await publisherInput.setValue('Publisher')
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
        if (config.params?.name === 'Publisher One') {
          return success(config, { items: [{ id: 'p1', name: 'Publisher One' }] })
        }
        if (config.params?.name === 'Publisher Two') {
          return success(config, { items: [{ id: 'p2', name: 'Publisher Two' }] })
        }
        return success(config, {
          items: [{ id: 'p1', name: 'Publisher One' }, { id: 'p2', name: 'Publisher Two' }],
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
    const publisherInput = wrapper.get('[data-test="identify-publisher-name"]')
    await publisherInput.setValue('Publisher One')
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
  })
  it('switches publishers with visible native selection and linked journals', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options') {
        return success(config, {
          items: [{ id: 'p1', name: 'Publisher One' }, { id: 'p2', name: 'Publisher Two' }],
        })
      }
      if (config.url === '/journals/options') {
        const publisherId = config.params?.publisher_id
        return success(config, {
          items: [{
            id: publisherId === 'p1' ? 'j1' : 'j2',
            publisher_id: publisherId,
            name: publisherId === 'p1' ? 'Journal One' : 'Journal Two',
            issn: null, eissn: null, website_url: null,
          }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    const publisherSelect = wrapper.get('[data-test="identify-publisher-name"]')
    expect(publisherSelect.element.tagName).toBe('SELECT')
    expect(publisherSelect.element.closest('label')).toBeNull()
    expect(wrapper.get('label[for="identify-publisher-name"]').text()).toBe('出版社名称')
    expect(publisherSelect.attributes('id')).toBe('identify-publisher-name')

    await publisherSelect.setValue('Publisher One')
    await flushPromises()
    expect((publisherSelect.element as HTMLSelectElement).value).toBe('Publisher One')
    expect(wrapper.findAll('#journal-options option').map((option) => option.attributes('value'))).toEqual(['Journal One'])
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal One')
    await wrapper.get('[data-test="identify-issn"]').setValue('03785955')
    await wrapper.get('[data-test="identify-eissn"]').setValue('18781128')

    await publisherSelect.setValue('Publisher Two')
    await flushPromises()
    expect((publisherSelect.element as HTMLSelectElement).value).toBe('Publisher Two')
    expect(wrapper.findAll('#journal-options option').map((option) => option.attributes('value'))).toEqual(['Journal Two'])
    expect((wrapper.get('[data-test="identify-journal-name"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('[data-test="identify-eissn"]').element as HTMLInputElement).value).toBe('')

    await publisherSelect.setValue('Publisher One')
    await flushPromises()
    expect((publisherSelect.element as HTMLSelectElement).value).toBe('Publisher One')
    expect(wrapper.findAll('#journal-options option').map((option) => option.attributes('value'))).toEqual(['Journal One'])
  })

  it('allows a new publisher name and returns to existing publisher choices', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options') {
        return success(config, { items: [{ id: 'p1', name: 'Publisher One' }] })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    const publisherSelect = wrapper.get('[data-test="identify-publisher-name"]')
    expect(publisherSelect.element.tagName).toBe('SELECT')

    await publisherSelect.setValue('__manual_publisher__')
    const publisherInput = wrapper.get('input[data-test="identify-publisher-name"]')
    await publisherInput.setValue('New Publisher')
    expect((publisherInput.element as HTMLInputElement).value).toBe('New Publisher')

    await wrapper.get('[data-test="select-existing-publisher"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-test="identify-publisher-name"]').element as HTMLSelectElement).value).toBe('')
    expect(wrapper.find('[data-test="identify-publisher-name"] option[value="Publisher One"]').exists()).toBe(true)
  })

  it('autofills a journal entered before publisher options finish loading', async () => {
    vi.useFakeTimers()
    let finishPublisherOptions: (() => void) | undefined
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options' && !config.params?.name) {
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
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Journal One')
    expect(finishPublisherOptions).toBeDefined()
    finishPublisherOptions?.()
    await flushPromises()
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('Publisher One')
    await flushPromises()

    expect((wrapper.get('[data-test="identify-issn"]').element as HTMLInputElement).value).toBe('03785955')
    expect((wrapper.get('[data-test="identify-eissn"]').element as HTMLInputElement).value).toBe('18781128')
    expect((wrapper.get('[data-test="identify-website"]').element as HTMLInputElement).value).toBe('https://journal.example')
  })

  it('polls network identification and confirms an external candidate', async () => {
    vi.useFakeTimers()
    const externalCandidate = {
      candidate_key: 'c1', name: 'Network Journal', publisher_name: 'Publisher',
      website_url: 'https://journal.example', author_guidelines_url: 'https://journal.example/guide',
      submission_url: 'https://www.editorialmanager.com/network', platform_code: 'EDITORIAL_MANAGER',
      portal_access_status: 'PUBLIC_ACCESS', identity_status: 'NEEDS_CONFIRMATION',
      match_reasons: ['官方页面名称匹配'], sources: ['OPENALEX', 'OFFICIAL_SITE'],
      evidence: [{ source_type: 'JOURNAL_HOME', url: 'https://journal.example', title: 'Network Journal', http_status: 200 }],
    }
    let pollCount = 0
    let finishFirstPoll: (() => void) | undefined
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-network', status: 'PENDING', candidates: [] })
      }
      if (config.url === '/tasks/task-network' && config.method === 'get') {
        pollCount += 1
        if (pollCount === 1) {
          const processingTask = {
            task_id: 'task-network', task_type: 'journal.identify', status: 'PROCESSING',
            progress: 45, stage: 'OFFICIAL_SITE_VERIFY', message: null,
            warnings: ['Crossref 暂时不可用'], candidates: [],
          }
          return new Promise<AxiosResponse>((resolve) => {
            finishFirstPoll = () => resolve(success(config, processingTask))
          })
        }
        return success(config, {
          task_id: 'task-network', task_type: 'journal.identify', status: 'SUCCEEDED',
          progress: 100, stage: 'PERSIST', message: null, warnings: [], candidates: [externalCandidate],
        })
      }
      if (config.url === '/tasks/task-network/confirm-candidate') {
        return success(config, {
          task_id: 'task-network', task_type: 'journal.identify', status: 'SUCCEEDED',
          progress: 100, stage: 'PERSIST', message: null, warnings: [], journal_id: 'j1',
          candidates: [{ ...externalCandidate, id: 'j1', identity_status: 'VERIFIED' }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Network Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    expect(finishFirstPoll).toBeDefined()
    finishFirstPoll?.()
    await flushPromises()
    expect(wrapper.get('[data-test="task-stage"]').text()).toContain('官网身份核验')
    expect(wrapper.get('[data-test="identification-progress"]').attributes('value')).toBe('45')
    expect(wrapper.text()).toContain('Crossref 暂时不可用')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.text()).toContain('EDITORIAL_MANAGER')
    expect(wrapper.text()).toContain('OPENALEX')
    expect(wrapper.find('a[href="https://journal.example/guide"]').exists()).toBe(true)
    await wrapper.get('[data-test="select-candidate-c1"]').setValue(true)
    await wrapper.get('[data-test="confirm-identity"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已验证')
    expectSaveSuccessToast()
  })

  it('keeps confirmation disabled when reusing an already confirmed task', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, {
          task_id: 'task-reused', status: 'SUCCEEDED', journal_id: 'j1',
          candidates: [{
            candidate_key: 'c2', name: 'Other Journal', identity_status: 'NEEDS_CONFIRMATION',
          }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Repeated Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="select-candidate-c2"]').setValue(true)
    expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
  })

  it('restarts a cancelled task', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-cancelled', status: 'CANCELLED', candidates: [] })
      }
      if (config.url === '/tasks/task-cancelled/retry') {
        return success(config, {
          task_id: 'task-cancelled', task_type: 'journal.identify', status: 'PENDING',
          progress: 0, message: null, candidates: [],
        })
      }
      if (config.url === '/tasks/task-cancelled') {
        return success(config, {
          task_id: 'task-cancelled', task_type: 'journal.identify', status: 'PENDING',
          progress: 0, message: null, candidates: [],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Cancelled Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    const retryButton = wrapper.get('[data-test="retry-task"]')
    expect(retryButton.text()).toBe('重新识别')
    await retryButton.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('识别任务状态：PENDING')
  })

  it('restarts a completed task that already has a journal', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, {
          task_id: 'task-completed', status: 'SUCCEEDED', journal_id: 'j1',
          candidates: [{ candidate_key: 'v1', id: 'j1', name: 'Completed Journal', identity_status: 'VERIFIED' }],
        })
      }
      if (config.url === '/tasks/task-completed/retry') {
        return success(config, {
          task_id: 'task-completed', task_type: 'journal.identify', status: 'PENDING',
          progress: 0, message: null, candidates: [],
        })
      }
      if (config.url === '/tasks/task-completed') {
        return success(config, {
          task_id: 'task-completed', task_type: 'journal.identify', status: 'PENDING',
          progress: 0, message: null, candidates: [],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Completed Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    const retryButton = wrapper.get('[data-test="retry-task"]')
    expect(retryButton.text()).toBe('重新识别')
    await retryButton.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('识别任务状态：PENDING')
  })

  it('allows retrying an unresolved task without a journal', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, {
          task_id: 'task-unknown', status: 'SUCCEEDED',
          candidates: [{ candidate_key: 'u1', name: 'Unknown Journal', identity_status: 'UNKNOWN' }],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Unknown Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="retry-task"]').exists()).toBe(true)
  })

  it('shows completion instead of waiting when a terminal task has no stage', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-complete', status: 'SUCCEEDED', candidates: [] })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Completed Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="identification-progress"]').attributes('value')).toBe('100')
    expect(wrapper.get('[data-test="task-stage"]').text()).toContain('识别完成')
    expect(wrapper.get('[data-test="task-stage"]').text()).not.toContain('等待 Worker')
  })

  it('continues polling until a running cancellation reaches a terminal state', async () => {
    vi.useFakeTimers()
    let cancellationRequested = false
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-cancel', status: 'PENDING', candidates: [] })
      }
      if (config.url === '/tasks/task-cancel/cancel') {
        cancellationRequested = true
        return success(config, {
          task_id: 'task-cancel', task_type: 'journal.identify', status: 'PROCESSING',
          progress: 50, message: null, candidates: [],
        })
      }
      if (config.url === '/tasks/task-cancel') {
        return success(config, {
          task_id: 'task-cancel', task_type: 'journal.identify',
          status: cancellationRequested ? 'CANCELLED' : 'PROCESSING',
          progress: 50, message: null, candidates: [],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Cancel Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.text()).toContain('识别任务状态：CANCELLED')
  })

  it('recovers polling after a transient task query failure', async () => {
    vi.useFakeTimers()
    let pollCount = 0
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-recover', status: 'PENDING', candidates: [] })
      }
      if (config.url === '/tasks/task-recover') {
        pollCount += 1
        if (pollCount === 1) throw new Error('offline')
        return success(config, {
          task_id: 'task-recover', task_type: 'journal.identify', status: 'SUCCEEDED',
          progress: 100, message: null, candidates: [],
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Recover Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.text()).toContain('无法查询识别任务进度')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(pollCount).toBe(2)
    expect(wrapper.text()).toContain('识别任务状态：SUCCEEDED')
  })

  it('disables clearing while a retry response is pending', async () => {
    vi.useFakeTimers()
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return success(config, { task_id: 'task-retry', status: 'PENDING', candidates: [] })
      }
      if (config.url === '/tasks/task-retry' && config.method === 'get') {
        return success(config, {
          task_id: 'task-retry', task_type: 'journal.identify', status: 'FAILED',
          progress: 50, message: 'outage', retryable: true, candidates: [],
        })
      }
      if (config.url === '/tasks/task-retry/retry') {
        return new Promise<AxiosResponse>(() => {})
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Retry Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    expect(wrapper.get('[data-test="clear-identification"]').attributes('disabled')).toBeDefined()
  })

  it('does not poll when an identify response arrives after unmount', async () => {
    vi.useFakeTimers()
    let finishIdentify: (() => void) | undefined
    adapter.mockImplementation(async (config) => {
      if (config.url === '/journals/identify') {
        return new Promise<AxiosResponse>((resolve) => {
          finishIdentify = () => resolve(success(config, {
            task_id: 'task-unmounted', status: 'PENDING', candidates: [],
          }))
        })
      }
      return success(config, emptyPage)
    })
    const wrapper = mount(JournalIdentificationPanel)
    await flushPromises()
    await wrapper.get('[data-test="identify-journal-name"]').setValue('Unmount Journal')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    wrapper.unmount()
    finishIdentify?.()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    expect(adapter.mock.calls.some(([config]) => config.url === '/tasks/task-unmounted')).toBe(false)
  })

  it('clears identification state and ignores stale option responses', async () => {
    vi.useFakeTimers()
    let finishStaleOptions: (() => void) | undefined
    let delayPublisherOptions = false
    adapter.mockImplementation(async (config) => {
      if (config.url === '/publishers/options' && delayPublisherOptions) {
        delayPublisherOptions = false
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
      'identify-journal-name',
      'identify-issn',
      'identify-eissn',
      'identify-website',
    ]
    for (const selector of inputSelectors) {
      expect((wrapper.get(`[data-test="${selector}"]`).element as HTMLInputElement).value).toBe('')
    }
    expect((publisherInput.element as HTMLSelectElement).value).toBe('')
    expect((wrapper.get('input[maxlength="100"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.findAll('[data-test="identity-candidate"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('识别任务状态：')
    expect(wrapper.find('textarea').exists()).toBe(false)

    await publisherInput.setValue('__manual_publisher__')
    const stalePublisherInput = wrapper.get('input[data-test="identify-publisher-name"]')
    await stalePublisherInput.setValue('Stale Publisher')
    delayPublisherOptions = true
    await wrapper.get('[data-test="select-existing-publisher"]').trigger('click')
    expect(finishStaleOptions).toBeDefined()
    await wrapper.get('[data-test="clear-identification"]').trigger('click')
    await flushPromises()
    finishStaleOptions?.()
    await flushPromises()
    expect((wrapper.get('[data-test="identify-publisher-name"]').element as HTMLSelectElement).value).toBe('')
    expect(wrapper.find('[data-test="identify-publisher-name"] option[value="Stale Publisher"]').exists()).toBe(false)
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
    await wrapper.get('[data-test="identify-publisher-name"]').setValue('__manual_publisher__')
    const publisherInput = wrapper.get('input[data-test="identify-publisher-name"]')
    await publisherInput.setValue('Publisher')
    await wrapper.get('[data-test="identify-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('标识冲突')
    expect(wrapper.get('[data-test="confirm-identity"]').attributes('disabled')).toBeDefined()
    expect(adapter.mock.calls.filter(([config]) => config.method === 'post')).toHaveLength(1)
  })
})
