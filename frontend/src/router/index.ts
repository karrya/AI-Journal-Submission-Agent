import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
  type Router,
  type RouterHistory,
} from 'vue-router'
import { registerAuthNavigationHandlers } from '../api/client'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/auth/LoginView.vue'),
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('../views/auth/ChangePasswordView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/authors',
    name: 'author-list',
    component: () => import('../views/authors/AuthorListView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/authors/:authorId/authorizations',
    name: 'author-authorizations',
    component: () => import('../views/authors/AuthorizationView.vue'),
    props: (route) => ({ authorId: String(route.params.authorId) }),
    meta: { requiresAuth: true },
  },
  {
    path: '/authors/:authorId',
    name: 'author-detail',
    component: () => import('../views/authors/AuthorDetailView.vue'),
    props: (route) => ({ authorId: String(route.params.authorId) }),
    meta: { requiresAuth: true },
  },
  {
    path: '/authorizations',
    name: 'authorization-list',
    component: () => import('../views/authors/AuthorizationView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/journals',
    name: 'journal-list',
    component: () => import('../views/journals/JournalListView.vue'),
    meta: { requiresAuth: true },
  },
  { path: '/', redirect: '/dashboard' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })

  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    await auth.restoreSession().catch(() => null)

    if (auth.user?.must_change_password && to.name !== 'change-password') {
      return { name: 'change-password' }
    }
    if (to.meta.requiresAuth && !auth.user) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (to.name === 'login' && auth.user) {
      return { name: 'dashboard' }
    }
    return true
  })

  registerAuthNavigationHandlers({
    login: () => replaceAuthRoute(router, 'login'),
    changePassword: () => replaceAuthRoute(router, 'change-password'),
  })

  return router
}

async function replaceAuthRoute(router: Router, name: 'login' | 'change-password'): Promise<void> {
  if (router.currentRoute.value.name === name) return
  try {
    await router.replace({ name })
  } catch {
    // Preserve the original API error when navigation is duplicated or cancelled.
  }
}

export default createAppRouter()
