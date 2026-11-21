import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const skillDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(skillDir, '../../..')
const baseUrl = (process.env.ASA_RUN_URL ?? 'http://127.0.0.1:5173').replace(/\/$/, '')
const outputDir = resolve(process.env.ASA_RUN_OUTPUT ?? '/tmp/ai-journal-submission-agent-run')
const chromePath = process.env.CHROME_PATH
  ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds))

const user = {
  id: 'browser-user',
  username: 'browser-check',
  display_name: 'Browser Check',
  roles: ['system_admin'],
  status: 'active',
  must_change_password: false,
  last_login_at: null,
}
const owner = {
  id: 'browser-owner',
  display_name: 'Synthetic Owner',
  alternate_names: [],
  status: 'active',
  orcid: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}
const publisher = {
  id: 'browser-publisher',
  name: 'Synthetic Publisher',
  website_url: 'https://publisher.example',
  notes: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}
const emptyPage = { items: [], page: 1, page_size: 20, total: 0 }

let vite = null
let viteExited = false
let viteError = null
let viteOutput = ''
let browser = null

async function serverResponds() {
  try {
    const response = await fetch(baseUrl, { signal: AbortSignal.timeout(1500) })
    return response.ok
  } catch {
    return false
  }
}

async function startViteIfNeeded() {
  if (await serverResponds()) return false
  const url = new URL(baseUrl)
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.protocol !== 'http:') {
    throw new Error(`No app responded at ${baseUrl}; automatic startup only supports local HTTP URLs.`)
  }

  vite = spawn('npm', [
    '--prefix', 'frontend', 'run', 'dev', '--',
    '--host', url.hostname, '--port', url.port || '5173', '--strictPort',
  ], {
    cwd: projectRoot,
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  vite.on('error', (error) => { viteError = error })
  vite.on('exit', () => { viteExited = true })
  vite.stdout.on('data', (chunk) => { viteOutput += chunk })
  vite.stderr.on('data', (chunk) => { viteOutput += chunk })

  const deadline = Date.now() + 30_000
  while (Date.now() < deadline) {
    if (await serverResponds()) return true
    if (viteError) throw viteError
    if (viteExited) throw new Error(`Vite exited before becoming ready.\n${viteOutput}`)
    await delay(250)
  }
  throw new Error(`Vite did not become ready within 30 seconds.\n${viteOutput}`)
}

async function stopVite() {
  if (!vite || viteExited) return
  const exited = new Promise((resolveExit) => vite.once('exit', resolveExit))
  try {
    process.kill(-vite.pid, 'SIGTERM')
  } catch (error) {
    if (error.code !== 'ESRCH') throw error
  }
  await Promise.race([exited, delay(5000)])
}

function fulfill(route, data, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
}

async function mockApi(page) {
  await page.route('**/api/v1/**', (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() === 'GET' && path === '/api/v1/auth/me') return fulfill(route, user)
    if (request.method() === 'GET' && path === '/api/v1/auth/csrf') return fulfill(route, { csrf_token: 'browser-check' })
    if (request.method() === 'GET' && path === '/api/v1/manuscripts') return fulfill(route, emptyPage)
    if (request.method() === 'GET' && path === '/api/v1/authors') {
      return fulfill(route, { ...emptyPage, items: [owner], total: 1 })
    }
    if (request.method() === 'GET' && path === '/api/v1/publishers') {
      return fulfill(route, { ...emptyPage, items: [publisher], total: 1 })
    }
    if (request.method() === 'GET' && path === '/api/v1/journals') return fulfill(route, emptyPage)
    if (request.method() === 'GET' && path === '/api/v1/registration/publishers') return fulfill(route, { items: [] })
    if (request.method() === 'GET' && path === '/api/v1/registration/tasks') return fulfill(route, emptyPage)
    if (request.method() === 'GET' && path === '/api/v1/author-authorizations/options') {
      return fulfill(route, { authors: [], users: [] })
    }
    return fulfill(route, { detail: `Unexpected browser-check request: ${request.method()} ${path}` }, 500)
  })
}

async function waitForDialogAnimation(page) {
  await page.locator('.el-overlay-dialog').evaluate(async (overlayDialog) => {
    await Promise.allSettled(overlayDialog.getAnimations().map((animation) => animation.finished))
  })
}

async function checkCenteredModal(page, { path, trigger, title, screenshot, beforeOpen, viewportHeight = 720 }) {
  await page.setViewportSize({ width: 1440, height: viewportHeight })
  await page.goto(`${baseUrl}${path}`)
  if (beforeOpen) await beforeOpen(page)
  await page.locator(trigger).click()
  await page.getByRole('dialog', { name: title }).waitFor()
  await waitForDialogAnimation(page)
  const metrics = await page.evaluate(() => {
    const dialogRect = document.querySelector('.el-dialog.app-dialog').getBoundingClientRect()
    return {
      top: dialogRect.top,
      bottom: dialogRect.bottom,
      height: dialogRect.height,
      viewportHeight: innerHeight,
    }
  })
  assert(metrics.height < metrics.viewportHeight, `${title} should not fill the viewport height`)
  assert(metrics.height <= metrics.viewportHeight * 0.88 + 1, `${title} exceeds its maximum height`)
  assert(metrics.top >= 0 && metrics.bottom <= metrics.viewportHeight, `${title} is clipped by the viewport`)
  assert(Math.abs(metrics.top - (metrics.viewportHeight - metrics.bottom)) <= 1, `${title} is not vertically centered`)
  await page.screenshot({ path: resolve(outputDir, screenshot) })
  return metrics
}

async function runBrowserCheck() {
  await mkdir(outputDir, { recursive: true })
  browser = await chromium.launch({ executablePath: chromePath, headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 720 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await mockApi(page)

  await page.goto(`${baseUrl}/manuscripts`)
  await page.locator('#manuscript-list-title').waitFor()
  await page.locator('[data-test="add-manuscript"]').click()
  await page.getByRole('dialog', { name: '创建稿件' }).waitFor()
  await page.locator('[data-test="owner-author"]').selectOption(owner.id)
  await waitForDialogAnimation(page)

  const desktop = await page.evaluate(() => {
    const overlay = document.querySelector('.el-overlay')
    const dialog = document.querySelector('.el-dialog.app-dialog')
    const body = document.querySelector('.app-dialog .el-dialog__body')
    const pageRoot = document.querySelector('.management-page')
    const overlayRect = overlay.getBoundingClientRect()
    const dialogRect = dialog.getBoundingClientRect()
    return {
      overlayParentIsBody: overlay.parentElement === document.body,
      overlayInsideAnimatedPage: pageRoot.contains(overlay),
      overlay: { top: overlayRect.top, left: overlayRect.left, width: overlayRect.width, height: overlayRect.height },
      dialog: { top: dialogRect.top, bottom: dialogRect.bottom, height: dialogRect.height },
      viewport: { width: innerWidth, height: innerHeight },
      bodyClientHeight: body.clientHeight,
      bodyScrollHeight: body.scrollHeight,
    }
  })
  assert.equal(desktop.overlayParentIsBody, true)
  assert.equal(desktop.overlayInsideAnimatedPage, false)
  assert.equal(desktop.overlay.top, 0)
  assert.equal(desktop.overlay.left, 0)
  assert.equal(desktop.overlay.width, desktop.viewport.width)
  assert.equal(desktop.overlay.height, desktop.viewport.height)
  assert(desktop.dialog.top >= 0 && desktop.dialog.bottom <= desktop.viewport.height)
  assert(desktop.dialog.height < desktop.viewport.height, 'Wide dialog should fit its content instead of forcing full viewport height')
  assert(Math.abs(desktop.dialog.top - (desktop.viewport.height - desktop.dialog.bottom)) <= 1, 'Dialog should be vertically centered')
  assert(desktop.bodyScrollHeight > desktop.bodyClientHeight, 'Basic step should scroll at 720px viewport height')
  await page.screenshot({ path: resolve(outputDir, 'create-dialog-basic.png') })

  const scrollTop = await page.locator('.app-dialog .el-dialog__body').evaluate((body) => {
    body.scrollTop = body.scrollHeight
    return body.scrollTop
  })
  assert(scrollTop > 0, 'Dialog body did not scroll')
  await page.screenshot({ path: resolve(outputDir, 'create-dialog-scrolled.png') })

  await page.locator('[data-test="create-step-next"]').click()
  await page.locator('[data-test="create-step-declarations"]').waitFor()
  assert.equal(await page.locator('[data-test="create-step-basic"]').count(), 0)
  await page.screenshot({ path: resolve(outputDir, 'create-dialog-declarations.png') })

  await page.locator('[data-test="create-step-next"]').click()
  await page.locator('[data-test="create-step-authors"]').waitFor()
  await page.locator('[data-test="create-authorship-form"]').waitFor()
  await page.screenshot({ path: resolve(outputDir, 'create-dialog-authors.png') })

  await page.locator('[data-test="create-step-prev"]').click()
  await page.locator('[data-test="create-step-declarations"]').waitFor()
  await page.locator('[data-test="create-step-prev"]').click()
  await page.locator('[data-test="create-step-basic"]').waitFor()
  assert.equal(await page.locator('[data-test="owner-author"]').inputValue(), owner.id)

  await page.locator('[data-test="create-step-next"]').click()
  await page.locator('[data-test="create-step-next"]').click()
  await page.locator('[data-test="create-step-authors"]').waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  await waitForDialogAnimation(page)
  const mobile = await page.evaluate(() => {
    const dialogRect = document.querySelector('.el-dialog.app-dialog').getBoundingClientRect()
    return {
      left: dialogRect.left,
      right: dialogRect.right,
      top: dialogRect.top,
      bottom: dialogRect.bottom,
      height: dialogRect.height,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
      documentClientWidth: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
    }
  })
  assert(mobile.left >= 0 && mobile.right <= mobile.viewportWidth)
  assert(mobile.height < mobile.viewportHeight)
  assert(Math.abs(mobile.top - (mobile.viewportHeight - mobile.bottom)) <= 1, 'Mobile dialog should be vertically centered')
  assert(mobile.documentScrollWidth <= mobile.documentClientWidth)
  await page.screenshot({ path: resolve(outputDir, 'create-dialog-mobile.png') })

  const additionalModals = {
    author: await checkCenteredModal(page, {
      path: '/authors', trigger: '[data-test="add-author"]', title: '添加作者', screenshot: 'add-author.png', viewportHeight: 1000,
    }),
    journal: await checkCenteredModal(page, {
      path: '/journals', trigger: '[data-test="add-journal"]', title: '添加期刊', screenshot: 'add-journal.png', viewportHeight: 1000,
      beforeOpen: async (browserPage) => { await browserPage.locator('[data-test="journals-tab"]').click() },
    }),
    registration: await checkCenteredModal(page, {
      path: '/registration', trigger: '[data-test="open-create-registration"]', title: '创建注册任务', screenshot: 'create-registration.png', viewportHeight: 1000,
    }),
  }
  assert.deepEqual(errors, [])

  const result = {
    status: 'passed',
    baseUrl,
    syntheticDataOnly: true,
    desktop,
    scrollTop,
    steps: '1 → 2 → 3 → 2 → 1 → 3',
    mobile,
    additionalModals,
    consoleErrors: errors,
    screenshots: outputDir,
  }
  await writeFile(resolve(outputDir, 'result.json'), `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify(result, null, 2))
  await context.close()
}

let startedVite = false
try {
  startedVite = await startViteIfNeeded()
  await runBrowserCheck()
} finally {
  if (browser) await browser.close()
  if (startedVite) await stopVite()
}
