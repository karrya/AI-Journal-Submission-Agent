import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from './index'
import { useAuthStore, type User } from '../stores/auth'

const activeUser: User = {
  id: 'u1',
  username: 'admin',
  display_name: 'Admin',
  roles: ['system_admin'],
  status: 'active',
  must_change_password: false,
  last_login_at: null,
}

describe('protected router', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('waits for session restoration before choosing a destination', async () => {
    const auth = useAuthStore()
    let finishRestore!: (user: User | null) => void
    const restore = vi.spyOn(auth, 'restoreSession').mockImplementationOnce(
      () => new Promise<User | null>((resolve) => { finishRestore = resolve }),
    ).mockResolvedValue(null)
    const router = createAppRouter(createMemoryHistory())

    const navigation = router.push('/dashboard')
    await vi.waitFor(() => expect(restore).toHaveBeenCalledOnce())
    expect(router.currentRoute.value.name).not.toBe('dashboard')

    finishRestore(null)
    await navigation
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('redirects an unauthenticated protected navigation to login', async () => {
    const auth = useAuthStore()
    vi.spyOn(auth, 'restoreSession').mockResolvedValue(null)
    const router = createAppRouter(createMemoryHistory())

    await router.push('/dashboard')

    expect(router.currentRoute.value.name).toBe('login')
  })

  it('forces a first-password change before dashboard access', async () => {
    const auth = useAuthStore()
    auth.setSession({ ...activeUser, must_change_password: true }, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/dashboard')

    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('redirects an authenticated user away from login', async () => {
    const auth = useAuthStore()
    auth.setSession(activeUser, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('exposes protected author, authorization, and journal management routes', async () => {
    const auth = useAuthStore()
    auth.setSession(activeUser, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/authors')
    expect(router.currentRoute.value.name).toBe('author-list')
    await router.push('/authors/a1')
    expect(router.currentRoute.value.name).toBe('author-detail')
    expect(router.currentRoute.value.params.authorId).toBe('a1')
    await router.push('/authors/a1/authorizations')
    expect(router.currentRoute.value.name).toBe('author-authorizations')
    expect(router.currentRoute.value.params.authorId).toBe('a1')
    await router.push('/authorizations')
    expect(router.currentRoute.value.name).toBe('authorization-list')
    await router.push('/journals')
    expect(router.currentRoute.value.name).toBe('journal-list')
  })

  it('exposes manuscript list and detail workflows', async () => {
    const auth = useAuthStore()
    auth.setSession(activeUser, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/manuscripts')
    expect(router.currentRoute.value.name).toBe('manuscript-list')
    await router.push('/manuscripts/m1')
    expect(router.currentRoute.value.name).toBe('manuscript-detail')
    expect(router.currentRoute.value.params.manuscriptId).toBe('m1')
  })

  it.each(['system_admin', 'auditor'])('allows %s to inspect audit logs', async (role) => {
    const auth = useAuthStore()
    auth.setSession({ ...activeUser, roles: [role] }, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/audit')
    expect(router.currentRoute.value.name).toBe('audit-list')
  })

  it('redirects business roles away from audit routes', async () => {
    const auth = useAuthStore()
    auth.setSession({ ...activeUser, roles: ['submission_operator'] }, 'csrf')
    const router = createAppRouter(createMemoryHistory())

    await router.push('/audit')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })
})
