import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from '../../api/client'
import DashboardView from './DashboardView.vue'

function success(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

const stubs = { RouterLink: { template: '<a><slot /></a>' } }

describe('DashboardView', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
  })

  it('renders only returned aggregates and safe recent operations', async () => {
    adapter.mockImplementation(async (config) => success(config, {
      author_count: 7, manuscript_count: 11, current_version_file_count: 13,
      expiring_authorization_count: 2,
      recent_operations: [{
        action: 'manuscript.update', target_id: 'm1', result: 'success',
        created_at: '2026-11-01T00:00:00Z', after_summary: { notes: 'private-dashboard-notes' },
      }],
      unapproved_count: 999,
    }))
    const wrapper = mount(DashboardView, { global: { stubs } })
    await flushPromises()

    expect(adapter.mock.calls[0][0]).toMatchObject({ method: 'get', url: '/dashboard/summary' })
    expect(wrapper.get('[data-test="author-count"]').text()).toBe('7')
    expect(wrapper.get('[data-test="manuscript-count"]').text()).toBe('11')
    expect(wrapper.get('[data-test="file-count"]').text()).toBe('13')
    expect(wrapper.get('[data-test="expiring-count"]').text()).toBe('2')
    expect(wrapper.text()).toContain('manuscript.update')
    expect(wrapper.text()).not.toContain('private-dashboard-notes')
    expect(wrapper.text()).not.toContain('999')
  })

  it('does not fabricate zero aggregates when the summary request fails', async () => {
    adapter.mockRejectedValue(new Error('offline'))
    const wrapper = mount(DashboardView, { global: { stubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('无法加载工作台')
    expect(wrapper.find('[data-test="author-count"]').exists()).toBe(false)
  })
})
