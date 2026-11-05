import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore, type User } from './stores/auth'
import App from './App.vue'

const user: User = {
  id: 'u1', username: 'user', display_name: 'User', roles: ['submission_operator'],
  status: 'active', must_change_password: false, last_login_at: null,
}
const global = {
  plugins: [createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    RouterView: true,
    ElContainer: { template: '<div><slot /></div>' },
    ElHeader: { template: '<header><slot /></header>' },
    ElMain: { template: '<main><slot /></main>' },
    ElButton: { template: '<button><slot /></button>' },
  },
}

describe('App navigation', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('links business users to manuscripts but not audit logs', () => {
    useAuthStore().setSession(user, 'csrf')
    const wrapper = mount(App, { global })

    expect(wrapper.text()).toContain('稿件')
    expect(wrapper.text()).not.toContain('审计日志')
  })

  it('links auditors to the read-only audit workflow', () => {
    useAuthStore().setSession({ ...user, roles: ['auditor'] }, 'csrf')
    const wrapper = mount(App, { global })

    expect(wrapper.text()).toContain('审计日志')
  })
})
