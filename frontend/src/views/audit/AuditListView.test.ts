import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from '../../api/client'
import AuditListView from './AuditListView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

const log = {
  id: 'l1', actor_user_id: 'u1', actor_type: 'user', category: 'business',
  action: 'manuscript.update', target_type: 'manuscript', target_id: 'm1', author_id: 'a1',
  request_id: '123e4567-e89b-12d3-a456-426614174000', result: 'success',
  before_summary: { title: 'Before' }, after_summary: { title: 'After' },
  created_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }

describe('AuditListView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  it('queries approved audit filters with server pagination', async () => {
    adapter.mockImplementation(async (config) => success(config, { ...emptyPage, items: [log], total: 21 }))
    const wrapper = mount(AuditListView)
    await flushPromises()
    await wrapper.get('[data-test="audit-actor"]').setValue(' u1 ')
    await wrapper.get('[data-test="audit-category"]').setValue('business')
    await wrapper.get('[data-test="audit-action"]').setValue(' manuscript.update ')
    await wrapper.get('[data-test="audit-result"]').setValue('success')
    await wrapper.get('[data-test="audit-created-from"]').setValue('2026-11-01T00:00')
    await wrapper.get('[data-test="apply-audit-filters"]').trigger('click')
    await flushPromises()

    const query = adapter.mock.calls.at(-1)?.[0].params
    expect(query).toMatchObject({
      page: 1, page_size: 20, actor_user_id: 'u1', category: 'business',
      action: 'manuscript.update', result: 'success', sort: 'created_at', order: 'desc',
    })
    expect(query.created_from).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    await wrapper.get('[data-test="next-audit"]').trigger('click')
    await flushPromises()
    expect(adapter.mock.calls.at(-1)?.[0].params.page).toBe(2)
  })

  it('shows read-only audit details without edit or delete controls', async () => {
    adapter.mockImplementation(async (config) => {
      if (config.url === '/audit-logs/l1') return success(config, log)
      return success(config, { ...emptyPage, items: [log], total: 1 })
    })
    const wrapper = mount(AuditListView)
    await flushPromises()
    expect(wrapper.get('[data-test="view-audit-l1"]').classes()).toContain('action-button--view')
    await wrapper.get('[data-test="view-audit-l1"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="audit-detail"]').text()).toContain('Before')
    expect(wrapper.get('[data-test="audit-detail"]').text()).toContain('After')
    expect(wrapper.get('tbody').text()).toContain('稿件')
    expect(wrapper.get('tbody').text()).not.toContain('manuscript\nm1')
    expect(wrapper.findAll('button').some((button) => /编辑|删除/.test(button.text()))).toBe(false)
  })

  it('ignores a detail response that finishes after newer filters are applied', async () => {
    let finishDetail!: () => void
    adapter.mockImplementation(async (config) => {
      if (config.url === '/audit-logs/l1') {
        return new Promise<AxiosResponse>((resolve) => {
          finishDetail = () => resolve(success(config, log))
        })
      }
      return success(config, { ...emptyPage, items: [log], total: 1 })
    })
    const wrapper = mount(AuditListView)
    await flushPromises()
    await wrapper.get('[data-test="view-audit-l1"]').trigger('click')
    await wrapper.get('[data-test="apply-audit-filters"]').trigger('click')
    await flushPromises()

    finishDetail()
    await flushPromises()
    expect(wrapper.find('[data-test="audit-detail"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="view-audit-l1"]').attributes('disabled')).toBeUndefined()
  })

  it('omits blank filters and does not show an empty state on failure', async () => {
    adapter.mockRejectedValue(new Error('offline'))
    const wrapper = mount(AuditListView)
    await flushPromises()

    expect(adapter.mock.calls[0][0].params.actor_user_id).toBeUndefined()
    expect(wrapper.text()).toContain('无法加载审计日志')
    expect(wrapper.text()).not.toContain('未找到审计日志')
  })
})
