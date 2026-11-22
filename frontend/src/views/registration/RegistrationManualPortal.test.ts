import { flushPromises, mount } from '@vue/test-utils'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../../api/client'
import { useAuthStore, type User } from '../../stores/auth'
import RegistrationView from './RegistrationView.vue'

const now = '2026-11-22T00:00:00Z'
const admin: User = {
  id: 'admin-1', username: 'admin', display_name: 'Administrator', roles: ['system_admin'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const publisher = {
  id: 'support-1', publisher_id: 'p1', publisher_code: 'ELSEVIER', display_name: 'Elsevier',
  support_status: 'SUPPORTED', support_level: 'V0_1', official_domains: ['elsevier.example'],
  notes: null, created_at: now, updated_at: now,
}
const journal = {
  id: 'j1', publisher_id: 'p1', name: 'Journal of Tests', issn: '1234-5678', eissn: null,
  website_url: 'https://journal.example',
}
const createdPortal = {
  id: 'portal-manual', journal_id: 'j1', original_url: 'https://register.example/start',
  final_url: 'https://register.example/start', redirect_chain: [], verification_status: 'VERIFIED',
  access_status: 'MANUALLY_VERIFIED', platform_code: 'EM', confidence: 1,
  adapter_code: 'EM_ADAPTER', adapter_name: 'Editorial Manager', adapter_version: '1.0.0',
  adapter_support_status: 'SUPPORTED', adapter_allowed_domains: ['register.example'],
  adapter_last_verified_at: now, support_status: 'SUPPORTED', evidence_summary: [],
}
const authorization = {
  id: 'grant-1', author_id: 'a1', user_id: 'admin-1', permissions: ['account:register'],
  valid_from: '2026-11-01T00:00:00Z', valid_to: '2099-01-01T00:00:00Z', evidence_ref: null,
  notes: null, revoked_at: null, reviewed_by: null, reviewed_at: null, created_at: now,
  updated_at: now, validity_status: 'active',
}

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

function page(items: object[]) {
  return { items, page: 1, page_size: 20, total: items.length }
}

describe('RegistrationView manual portal verification', () => {
  it('creates a manually verified portal without creating a registration task', async () => {
    setActivePinia(createPinia())
    useAuthStore().setSession(admin, 'csrf')
    const adapter = vi.fn<AxiosAdapter>(async (config) => {
      if (config.url === '/registration/publishers') return success(config, { items: [publisher] })
      if (config.url === '/registration/publishers/p1/journals') return success(config, { items: [journal] })
      if (config.method === 'get' && config.url === '/journals/j1/submission-portals') return success(config, { items: [] })
      if (config.method === 'post' && config.url === '/journals/j1/submission-portals') return success(config, createdPortal, 201)
      if (config.url === '/registration/tasks') return success(config, page([]))
      if (config.url === '/author-authorizations/options') return success(config, { authors: [{ id: 'a1', display_name: 'Author One' }], users: [] })
      if (config.url === '/author-authorizations') return success(config, page([authorization]))
      if (config.url === '/authors/a1/emails') return success(config, page([]))
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })
    api.defaults.adapter = adapter
    const wrapper = mount(RegistrationView, {
      attachTo: document.body,
      global: { stubs: { teleport: true, transition: false } },
    })
    await flushPromises()
    await wrapper.get('[data-test="open-create-registration"]').trigger('click')
    await wrapper.get('[data-test="registration-publisher"]').setValue('p1')
    await flushPromises()
    await wrapper.get('[data-test="registration-journal"]').setValue('j1')
    await flushPromises()

    await wrapper.get('[data-test="manual-portal-toggle"]').trigger('click')
    await wrapper.get('[data-test="manual-portal-url"]').setValue(createdPortal.final_url)
    await wrapper.get('[data-test="manual-platform-code"]').setValue('EM')
    await wrapper.get('[data-test="manual-adapter-code"]').setValue('EM_ADAPTER')
    await wrapper.get('[data-test="manual-adapter-name"]').setValue('Editorial Manager')
    await wrapper.get('[data-test="manual-adapter-version"]').setValue('1.0.0')
    await wrapper.get('[data-test="manual-allowed-domains"]').setValue('register.example')
    await wrapper.get('[data-test="manual-verification-notes"]').setValue('Verified manually without automated page access')
    await wrapper.get('[data-test="manual-portal-form"]').trigger('submit')
    expect(adapter.mock.calls.some(([config]) => config.method === 'post')).toBe(false)
    expect(wrapper.get('[data-test="manual-portal-error"]').text()).toContain('请确认已人工核验')

    await wrapper.get('[data-test="manual-portal-confirm"]').setValue(true)
    await wrapper.get('[data-test="manual-portal-form"]').trigger('submit')
    await flushPromises()

    const createCall = adapter.mock.calls.find(([config]) => (
      config.method === 'post' && config.url === '/journals/j1/submission-portals'
    ))
    expect(createCall).toBeDefined()
    expect(JSON.parse(String(createCall?.[0].data))).toEqual({
      final_url: createdPortal.final_url,
      platform_code: 'EM',
      adapter_code: 'EM_ADAPTER',
      adapter_name: 'Editorial Manager',
      adapter_version: '1.0.0',
      adapter_allowed_domains: ['register.example'],
      adapter_verification_notes: 'Verified manually without automated page access',
      verification_confirmed: true,
    })
    expect((wrapper.get('[data-test="registration-platform"]').element as HTMLSelectElement).value).toBe('portal-manual')
    expect(wrapper.find('[data-test="manual-portal-form"]').exists()).toBe(false)
    expect(adapter.mock.calls.some(([config]) => config.method === 'post' && config.url === '/registration/tasks')).toBe(false)
    wrapper.unmount()
  })
})
