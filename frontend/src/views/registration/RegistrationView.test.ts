import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import RegistrationView from './RegistrationView.vue'

const now = '2026-11-19T08:00:00Z'
const supportedPublisher = {
  id: 'support-1', publisher_id: 'p1', publisher_code: 'ELSEVIER', display_name: 'Elsevier',
  support_status: 'SUPPORTED', support_level: 'V0_1', official_domains: ['register.example'],
  notes: null, created_at: now, updated_at: now,
}
const unsupportedPublisher = {
  ...supportedPublisher, id: 'support-2', publisher_id: 'p2', publisher_code: 'WILEY',
  display_name: 'Wiley', support_status: 'TESTING', support_level: 'V0_2',
}
const supportedPortal = {
  id: 'portal-1', journal_id: 'j1', original_url: 'https://register.example/start',
  final_url: 'https://register.example/register', redirect_chain: [], verification_status: 'VERIFIED',
  access_status: 'ACCESSIBLE', platform_code: 'EM', confidence: 1, evidence_summary: [],
  adapter_code: 'EM_ADAPTER', adapter_name: 'Editorial Manager', adapter_version: '1.0.0',
  adapter_support_status: 'SUPPORTED', adapter_allowed_domains: ['register.example'],
  adapter_last_verified_at: now, support_status: 'SUPPORTED',
}
const unsupportedPortal = {
  ...supportedPortal, id: 'portal-2', platform_code: 'TEST',
  adapter_code: 'TEST_ADAPTER', adapter_name: 'Unverified adapter', adapter_version: '1.0.0',
  adapter_support_status: 'DISABLED', support_status: 'DISABLED',
}
const journal = {
  id: 'j1', publisher_id: 'p1', name: 'Journal of Tests', issn: '1234-5678', eissn: null,
  website_url: 'https://journal.example',
}
const task = {
  id: 't1', author_id: 'a1', publisher_id: 'p1', journal_id: 'j1', platform_code: 'EM',
  task_status: 'PENDING', current_step: '等待执行', retryable: false, created_at: now,
}
const authorization = {
  id: 'grant-1', author_id: 'a1', user_id: 'u1', permissions: ['account:register'],
  valid_from: '2026-11-19T07:00:00Z', valid_to: '2026-11-20T07:00:00Z', evidence_ref: null,
  notes: null, revoked_at: null, reviewed_by: null, reviewed_at: null, created_at: now,
  updated_at: now, validity_status: 'active',
}
const email = {
  id: 'email-1', author_id: 'a1', email: 'author@example.com', normalized_email: 'author@example.com',
  purpose: 'registration', is_primary: true, verification_status: 'verified',
  authorization_status: 'authorized', created_at: now, updated_at: now,
}

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

function page(items: object[], total = items.length) {
  return { items, page: 1, page_size: 20, total }
}

describe('RegistrationView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>
  let wrappers: VueWrapper[]

  beforeEach(() => {
    setActivePinia(createPinia())
    wrappers = []
    adapter = vi.fn<AxiosAdapter>()
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') {
        return success(config, { items: [supportedPublisher, unsupportedPublisher] })
      }
      if (config.url === '/registration/publishers/p1/journals') return success(config, { items: [journal] })
      if (config.url === '/journals/j1/submission-portals') return success(config, { items: [supportedPortal, unsupportedPortal] })
      if (config.url === '/registration/publishers/p2/journals') return success(config, { items: [] })
      if (config.url === '/registration/tasks') return success(config, page([task]))
      if (config.url === '/author-authorizations/options') {
        return success(config, { authors: [{ id: 'a1', display_name: 'Author One' }], users: [{ id: 'u1', username: 'operator', display_name: 'Operator' }] })
      }
      if (config.url === '/author-authorizations') return success(config, page([authorization]))
      if (config.url === '/authors/a1/emails') return success(config, page([email]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    api.defaults.adapter = adapter
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
  })

  function mountView(): VueWrapper {
    const wrapper = mount(RegistrationView, { attachTo: document.body, global: { stubs: { teleport: true, transition: false } } })
    wrappers.push(wrapper)
    return wrapper
  }

  async function selectSupportedTarget(wrapper: VueWrapper): Promise<void> {
    await wrapper.get('[data-test="open-create-registration"]').trigger('click')
    await wrapper.get('[data-test="registration-author"]').setValue('a1')
    await flushPromises()
    await wrapper.get('[data-test="registration-publisher"]').setValue('p1')
    await flushPromises()
    await wrapper.get('[data-test="registration-journal"]').setValue('j1')
    await flushPromises()
    await wrapper.get('[data-test="registration-platform"]').setValue('portal-1')
  }

  it('shows workflow steps and disables unsupported targets without exposing secrets', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="registration-workflow"]').exists()).toBe(true)
    await wrapper.get('[data-test="open-create-registration"]').trigger('click')
    expect(wrapper.get('[data-test="unsupported-target"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="registration-platform"]').text()).toContain('请选择投稿平台')
    await selectSupportedTarget(wrapper)
    expect(wrapper.get('[data-test="unsupported-platform"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('授权核验')
    expect(wrapper.text()).toContain('人工确认')
    expect(wrapper.text()).not.toContain('credential_ref')
    expect(wrapper.text()).not.toContain('secret-credential-reference')
    expect(wrapper.text()).not.toContain('password')
    expect(wrapper.text()).not.toContain('secret-password')
    expect(wrapper.text().toLowerCase()).not.toContain('token')
    expect(wrapper.text()).not.toContain('https://register.example/verify?token=complete-secret-link')
    expect(wrapper.text()).not.toContain('author@example.com')
    expect(wrapper.find('[data-test="publisher-accounts"]').exists()).toBe(false)
    expect(adapter.mock.calls.some(([config]) => config.url === '/publisher-accounts')).toBe(false)
  })

  it('loads journals after publisher selection and submits a read-only confirmed target', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post' && config.url === '/registration/tasks') {
        return success(config, { ...task, id: 'created-task' }, 202)
      }
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher, unsupportedPublisher] })
      if (config.url === '/registration/publishers/p1/journals') return success(config, { items: [journal] })
      if (config.url === '/journals/j1/submission-portals') return success(config, { items: [supportedPortal, unsupportedPortal] })
      if (config.url === '/registration/tasks') return success(config, page([task]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [{ id: 'a1', display_name: 'Author One' }], users: [] })
      if (config.url === '/author-authorizations') return success(config, page([authorization]))
      if (config.url === '/authors/a1/emails') return success(config, page([email]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await selectSupportedTarget(wrapper)

    expect(adapter.mock.calls.some(([config]) => config.url === '/registration/publishers/p1/journals')).toBe(true)
    const summary = wrapper.get('[data-test="confirmation-summary"]')
    expect(summary.text()).toContain('Author One')
    expect(summary.text()).toContain('Journal of Tests')
    expect(summary.text()).toContain('Editorial Manager')
    expect(summary.text()).toContain('a•••@example.com')
    expect(summary.find('input').exists()).toBe(false)
    expect(summary.find('textarea').exists()).toBe(false)

    await wrapper.get('[data-test="create-registration-task"]').trigger('click')
    await flushPromises()
    const createCall = adapter.mock.calls.find(([config]) => config.method === 'post' && config.url === '/registration/tasks')
    const payload = JSON.parse(String(createCall?.[0].data))
    expect(payload).toMatchObject({
      author_id: 'a1', publisher_id: 'p1', journal_id: 'j1', authorization_id: 'grant-1', platform_code: 'EM',
    })
    expect(payload.idempotency_key.length).toBeGreaterThanOrEqual(16)
    expect(wrapper.text()).toContain('created-task')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('applies task status and time filters with timezone-aware dates', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="task-status-filter"]').setValue('FAILED')
    await wrapper.get('[data-test="created-from-filter"]').setValue('2026-11-18T08:00')
    await wrapper.get('[data-test="created-to-filter"]').setValue('2026-11-19T08:00')
    await wrapper.get('[data-test="apply-task-filters"]').trigger('click')
    await flushPromises()

    const request = adapter.mock.calls.filter(([config]) => config.url === '/registration/tasks').at(-1)?.[0]
    expect(request?.params).toMatchObject({ page: 1, task_status: 'FAILED' })
    expect(request?.params.created_from).toBe(new Date('2026-11-18T08:00').toISOString())
    expect(request?.params.created_to).toBe(new Date('2026-11-19T08:00').toISOString())
  })

  it('requires explicit cancellation confirmation and preserves Enter as a safe action', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url?.endsWith('/cancel')) return success(config, { ...task, task_status: 'CANCELLED', current_step: '用户取消' })
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page([task]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="cancel-task-t1"]').trigger('click')
    await wrapper.get('[data-test="confirm-cancel-t1"]').trigger('keydown.enter')
    expect(adapter.mock.calls.some(([config]) => config.url?.endsWith('/cancel'))).toBe(false)
    await wrapper.get('[data-test="cancel-confirmation"]').setValue(true)
    await wrapper.get('[data-test="confirm-cancel-t1"]').trigger('click')
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => config.method === 'post' && config.url === '/registration/tasks/t1/cancel')).toBe(true)
    expect(wrapper.get('[data-test="selected-task-status"]').text()).toContain('已取消')
  })

  it('keeps the cancellation dialog open with its error when cancellation fails', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url?.endsWith('/cancel')) throw new Error('cancel failed')
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page([task]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="cancel-task-t1"]').trigger('click')
    await wrapper.get('[data-test="cancel-confirmation"]').setValue(true)
    await wrapper.get('[data-test="confirm-cancel-t1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('无法取消')
    expect((wrapper.get('[data-test="cancel-confirmation"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('retries only an eligible failed task and renders the returned state', async () => {
    const failedTask = { ...task, task_status: 'FAILED', current_step: '网络暂时不可用', retryable: true }
    adapter.mockImplementation(async (config) => {
      if (config.url?.endsWith('/retry')) return success(config, { ...failedTask, task_status: 'PENDING', current_step: '重新执行', retryable: false })
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page([failedTask]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="retry-task-t1"]').trigger('click')
    await flushPromises()

    expect(adapter.mock.calls.some(([config]) => config.method === 'post' && config.url === '/registration/tasks/t1/retry')).toBe(true)
    expect(wrapper.get('[data-test="selected-task-status"]').text()).toContain('待执行')
  })

  it('groups manual intervention and presents consequence text without execution controls', async () => {
    const manualTasks = [
      { ...task, id: 'captcha', task_status: 'WAITING_CAPTCHA' },
      { ...task, id: 'submit', task_status: 'READY_TO_SUBMIT' },
      { ...task, id: 'email', task_status: 'WAITING_EMAIL_CONFIRM' },
      { ...task, id: 'review', task_status: 'NEEDS_MANUAL_REVIEW' },
    ]
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page(manualTasks))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="manual-captcha"]').text()).toContain('captcha')
    expect(wrapper.get('[data-test="manual-submit"]').text()).toContain('submit')
    expect(wrapper.get('[data-test="manual-email"]').text()).toContain('email')
    expect(wrapper.get('[data-test="manual-review"]').text()).toContain('review')
    expect(wrapper.get('[data-test="manual-submit"]').text()).toContain('后果')
    expect(wrapper.find('[data-test="execute-registration"]').exists()).toBe(false)
  })

  it('shows a loading skeleton and a useful empty state', async () => {
    let resolveTasks!: (value: AxiosResponse) => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/tasks') return new Promise<AxiosResponse>((resolve) => { resolveTasks = resolve })
      if (config.url === '/registration/publishers') return success(config, { items: [] })
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('[data-test="task-skeleton"]').attributes('role')).toBe('status')
    expect(wrapper.get('[data-test="registration-task-list"]').attributes('aria-busy')).toBe('true')

    resolveTasks(success({} as InternalAxiosRequestConfig, page([])))
    await flushPromises()
    expect(wrapper.find('[data-test="task-skeleton"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="task-empty"]').text()).toContain('清除筛选')
  })

  it('keeps current tasks on a refresh error and retries the same safe query', async () => {
    let failNext = false
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/tasks') {
        if (failNext) {
          failNext = false
          throw new Error('offline')
        }
        return success(config, page([task]))
      }
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    failNext = true
    await wrapper.get('[data-test="refresh-tasks"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="task-error"]').text()).toContain('无法加载注册任务')
    expect(wrapper.find('[data-test="task-t1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-empty"]').exists()).toBe(false)
    await wrapper.get('[data-test="retry-task-load"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="task-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="task-t1"]').exists()).toBe(true)
  })

  it('reuses the same idempotency key after a lost create response', async () => {
    let attempts = 0
    adapter.mockImplementation(async (config) => {
      if (config.method === 'post' && config.url === '/registration/tasks') {
        attempts += 1
        if (attempts === 1) throw new Error('response lost after server commit')
        return success(config, { ...task, id: 'created-after-retry' }, 202)
      }
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/publishers/p1/journals') return success(config, { items: [journal] })
      if (config.url === '/journals/j1/submission-portals') return success(config, { items: [supportedPortal, unsupportedPortal] })
      if (config.url === '/registration/tasks') return success(config, page([]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [{ id: 'a1', display_name: 'Author One' }], users: [] })
      if (config.url === '/author-authorizations') return success(config, page([authorization]))
      if (config.url === '/authors/a1/emails') return success(config, page([email]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await selectSupportedTarget(wrapper)

    await wrapper.get('[data-test="create-registration-task"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="task-error"]').text()).toContain('无法创建注册任务')
    await wrapper.get('[data-test="create-registration-task"]').trigger('click')
    await flushPromises()

    const payloads = adapter.mock.calls
      .filter(([config]) => config.method === 'post' && config.url === '/registration/tasks')
      .map(([config]) => JSON.parse(String(config.data)) as { idempotency_key: string })
    expect(payloads).toHaveLength(2)
    expect(payloads[1].idempotency_key).toBe(payloads[0].idempotency_key)
    expect(wrapper.text()).toContain('created-after-retry')
  })

  it('keeps only the latest target journals and clears loading when selection becomes empty', async () => {
    const secondPublisher = { ...supportedPublisher, id: 'support-2', publisher_id: 'p2', display_name: 'Second Publisher' }
    const secondJournal = { ...journal, id: 'j2', publisher_id: 'p2', name: 'Latest Journal' }
    const pending = new Map<string, (response: AxiosResponse) => void>()
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher, secondPublisher] })
      if (config.url?.match(/^\/registration\/publishers\/p[12]\/journals$/)) {
        return new Promise<AxiosResponse>((resolve) => { pending.set(config.url as string, resolve) })
      }
      if (config.url === '/registration/tasks') return success(config, page([]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="open-create-registration"]').trigger('click')
    const publisherSelect = wrapper.get('[data-test="registration-publisher"]')
    const journalSelect = wrapper.get('[data-test="registration-journal"]')

    await publisherSelect.setValue('p1')
    await publisherSelect.setValue('p2')
    pending.get('/registration/publishers/p2/journals')?.(success({} as InternalAxiosRequestConfig, { items: [secondJournal] }))
    await flushPromises()
    expect(journalSelect.text()).toContain('Latest Journal')
    pending.get('/registration/publishers/p1/journals')?.(success({} as InternalAxiosRequestConfig, { items: [journal] }))
    await flushPromises()
    expect(journalSelect.text()).toContain('Latest Journal')
    expect(journalSelect.text()).not.toContain('Journal of Tests')
    expect((journalSelect.element as HTMLSelectElement).disabled).toBe(false)

    await publisherSelect.setValue('p1')
    expect((journalSelect.element as HTMLSelectElement).disabled).toBe(true)
    await publisherSelect.setValue('')
    expect(journalSelect.text()).toContain('请选择期刊')
    expect(journalSelect.text()).not.toContain('正在加载期刊')
    pending.get('/registration/publishers/p1/journals')?.(success({} as InternalAxiosRequestConfig, { items: [journal] }))
    await flushPromises()
    expect(journalSelect.text()).not.toContain('Journal of Tests')
  })

  it('keeps only the latest filter-journal response during out-of-order completion', async () => {
    const secondPublisher = { ...supportedPublisher, id: 'support-2', publisher_id: 'p2', display_name: 'Second Publisher' }
    const secondJournal = { ...journal, id: 'j2', publisher_id: 'p2', name: 'Latest Filter Journal' }
    const pending = new Map<string, (response: AxiosResponse) => void>()
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher, secondPublisher] })
      if (config.url?.match(/^\/registration\/publishers\/p[12]\/journals$/)) {
        return new Promise<AxiosResponse>((resolve) => { pending.set(config.url as string, resolve) })
      }
      if (config.url === '/registration/tasks') return success(config, page([]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    const publisherFilter = wrapper.get('[data-test="task-publisher-filter"]')
    const journalFilter = wrapper.get('[data-test="task-journal-filter"]')

    await publisherFilter.setValue('p1')
    await publisherFilter.setValue('p2')
    pending.get('/registration/publishers/p2/journals')?.(success({} as InternalAxiosRequestConfig, { items: [secondJournal] }))
    await flushPromises()
    pending.get('/registration/publishers/p1/journals')?.(success({} as InternalAxiosRequestConfig, { items: [journal] }))
    await flushPromises()

    expect(journalFilter.text()).toContain('Latest Filter Journal')
    expect(journalFilter.text()).not.toContain('Journal of Tests')
    expect((journalFilter.element as HTMLSelectElement).disabled).toBe(false)
  })

  it.each(['FAILED', 'CANCELLED', 'EXPIRED'])('marks every workflow stage unknown for %s without inferring history', async (status) => {
    const terminalTask = { ...task, task_status: status, current_step: '流程终止' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page([terminalTask]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()

    const steps = wrapper.get('[data-test="registration-workflow"]').findAll('li')
    expect(steps).toHaveLength(5)
    steps.forEach((step) => {
      expect(step.text()).toContain('阶段未知')
      expect(step.text()).not.toContain('已完成')
      expect(step.attributes('aria-current')).toBeUndefined()
    })
    expect(wrapper.get('[data-test="selected-task-status"]').text()).toContain(status === 'FAILED' ? '执行失败' : status === 'CANCELLED' ? '已取消' : '已过期')
  })

  it('supports an Escape-dismissible evidence drawer and associated labels on a narrow viewport', async () => {
    window.innerWidth = 390
    window.dispatchEvent(new Event('resize'))
    const wrapper = mountView()
    await flushPromises()

    const controls = wrapper.findAll('select, input')
    controls.forEach((control) => {
      const id = control.attributes('id')
      expect(id).toBeTruthy()
      expect(wrapper.find(`label[for="${id}"]`).exists()).toBe(true)
    })
    await wrapper.get('[data-test="open-evidence-t1"]').trigger('click')
    const content = wrapper.get('[data-test="registration-content"]')
    const drawer = wrapper.get('[data-test="evidence-drawer"]')
    expect(content.attributes('inert')).toBeDefined()
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.attributes('aria-modal')).toBe('true')

    const closeButtons = drawer.findAll('button')
    expect(closeButtons).toHaveLength(2)
    const firstButton = closeButtons[0].element as HTMLButtonElement
    const lastButton = closeButtons[1].element as HTMLButtonElement
    for (let iteration = 0; iteration < 3; iteration += 1) {
      lastButton.focus()
      await drawer.trigger('keydown', { key: 'Tab' })
      expect(document.activeElement).toBe(firstButton)
    }
    for (let iteration = 0; iteration < 3; iteration += 1) {
      firstButton.focus()
      await drawer.trigger('keydown', { key: 'Tab', shiftKey: true })
      expect(document.activeElement).toBe(lastButton)
    }

    await drawer.trigger('keydown.esc')
    expect(wrapper.find('[data-test="evidence-drawer"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="registration-content"]').attributes('inert')).toBeUndefined()
    expect(document.activeElement).toBe(wrapper.get('[data-test="open-evidence-t1"]').element)
    expect(wrapper.get('[data-test="open-evidence-t1"]').attributes('type')).toBe('button')
  })
  it('scopes exact adapter versions to the selected journal without duplicate values', async () => {
    const secondPortal = {
      ...supportedPortal, id: 'portal-3', adapter_version: '2.0.0', adapter_name: 'Editorial Manager v2',
    }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/publishers/p1/journals') return success(config, { items: [journal] })
      if (config.url === '/journals/j1/submission-portals') return success(config, { items: [supportedPortal, secondPortal] })
      if (config.url === '/registration/tasks') return success(config, page([]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [{ id: 'a1', display_name: 'Author One' }], users: [] })
      if (config.url === '/author-authorizations') return success(config, page([authorization]))
      if (config.url === '/authors/a1/emails') return success(config, page([email]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="open-create-registration"]').trigger('click')
    const platformSelect = wrapper.get('[data-test="registration-platform"]')
    expect(platformSelect.findAll('option')).toHaveLength(1)
    expect((platformSelect.element as HTMLSelectElement).disabled).toBe(true)

    await wrapper.get('[data-test="registration-author"]').setValue('a1')
    await flushPromises()
    await wrapper.get('[data-test="registration-publisher"]').setValue('p1')
    await flushPromises()
    await wrapper.get('[data-test="registration-journal"]').setValue('j1')
    await flushPromises()

    const options = platformSelect.findAll('option')
    expect(options.map((option) => option.attributes('value'))).toEqual(['', 'portal-1', 'portal-3'])
    expect(new Set(options.map((option) => option.attributes('value'))).size).toBe(options.length)
    expect(platformSelect.text()).toContain('1.0.0')
    expect(platformSelect.text()).toContain('2.0.0')
  })

  it('maps PROCESSING to the execution phase and uses phase-one safe messages', async () => {
    const processingTask = { ...task, task_status: 'PROCESSING', current_step: 'CLAIMED' }
    adapter.mockImplementation(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [supportedPublisher] })
      if (config.url === '/registration/tasks') return success(config, page([processingTask]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [], users: [] })
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="selected-task-status"]').text()).toContain('正在处理')
    expect(wrapper.get('[data-test="registration-workflow"]').text()).toContain('当前阶段')
    expect(wrapper.text()).toContain('规则允许时自动执行注册')
  })

})
