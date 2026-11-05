const { chromium } = require('playwright-core')
const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const assert = require('assert/strict')

const base = 'http://127.0.0.1:5173'
const evidence = process.env.EVIDENCE_DIR
const fixture = JSON.parse(fs.readFileSync(process.env.FIXTURE_FILE, 'utf8'))
const privateValues = [
  'COAUTHOR_PRIVATE_NOTES',
  'coauthor-private@' + 'example.com',
  'coauthor-private-phone',
  'OWNER_PRIVATE_NOTES',
  'owner-private@' + 'example.com',
  'owner-private-phone',
]
const minimalFields = ['author_id', 'display_name', 'is_corresponding', 'position']
const secondPdf = Buffer.from('%PDF-1.5\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')
const events = []
const business = []
const requestSequences = new WeakMap()
const staleTimeline = []
let staleStarted = 0

function publicPath(url) {
  return new URL(url).pathname
}

function staleMark(event, details = {}) {
  staleTimeline.push({ event, elapsed_ms: Math.round(performance.now() - staleStarted), ...details })
}

function capturePage(actor, page) {
  page.on('request', (request) => {
    const requestPath = publicPath(request.url())
    if (!requestPath.startsWith('/api/v1/')) return
    const sequence = events.length + 1
    requestSequences.set(request, sequence)
    events.push({ sequence, event: 'request', actor, method: request.method(), path: requestPath })
    if (actor === 'stale' && request.method() === 'POST' && /\/api\/v1\/manuscripts\/[^/]+\/versions\/[^/]+\/files$/.test(requestPath)) {
      staleMark('stale_upload_request', { request_sequence: sequence })
    }
  })
  page.on('response', (response) => {
    const responsePath = publicPath(response.url())
    if (!responsePath.startsWith('/api/v1/')) return
    const contentType = response.headers()['content-type'] || ''
    const body = contentType.includes('application/json')
      ? response.text().then((text) => ({ text, json: JSON.parse(text) })).catch(() => null)
      : Promise.resolve(null)
    const sequence = events.length + 1
    events.push({
      sequence,
      event: 'response',
      actor,
      request_sequence: requestSequences.get(response.request()) || null,
      method: response.request().method(),
      path: responsePath,
      status: response.status(),
    })
    if (/^\/api\/v1\/(manuscripts|files|dashboard)/.test(responsePath)) {
      business.push({ sequence, actor, method: response.request().method(), path: responsePath, status: response.status(), body })
    }
    if (actor === 'stale' && response.request().method() === 'POST' && /\/api\/v1\/manuscripts\/[^/]+\/versions\/[^/]+\/files$/.test(responsePath)) {
      staleMark('stale_upload_response', { response_sequence: sequence, status: response.status() })
    }
  })
}

function walk(value, visitor) {
  if (Array.isArray(value)) return value.forEach((item) => walk(item, visitor))
  if (value && typeof value === 'object') {
    visitor(value)
    Object.values(value).forEach((item) => walk(item, visitor))
  }
}

async function scanNetwork() {
  const scanned = []
  const nonJson = []
  for (const entry of business.filter((candidate) => candidate.actor === 'operator')) {
    const body = await entry.body
    if (!body) {
      scanned.push(entry.sequence)
      nonJson.push(entry.sequence)
      continue
    }
    for (const marker of privateValues) assert(!body.text.includes(marker), `private marker leaked in ${entry.path}`)
    walk(body.json, (object) => {
      assert(!Object.hasOwn(object, 'storage_path'), `storage_path leaked in ${entry.path}`)
      assert(!Object.hasOwn(object, 'stored_filename'), `stored_filename leaked in ${entry.path}`)
    })
    scanned.push(entry.sequence)
  }
  return { scanned, nonJson }
}

async function assertChineseLabels(page, labels, scope) {
  const text = await page.locator('body').innerText()
  for (const label of labels) assert(text.includes(label), `Chinese UI label missing in ${scope}: ${label}`)
}

async function assertChineseAuditTable(page, scope) {
  await assertChineseLabels(page, ['审计日志', '只读操作历史', '应用筛选', '上一页', '下一页'], scope)
  const headings = await page.locator('thead').innerText()
  for (const label of ['创建时间', '操作者', '类别', '操作', '目标', '结果', '请求 ID', '详情']) {
    assert(headings.includes(label), `Chinese audit table heading missing in ${scope}: ${label}`)
  }
}

async function login(context, username, password, actor) {
  const page = await context.newPage()
  capturePage(actor, page)
  await page.goto(`${base}/login`)
  await page.locator('[data-test="username"]').fill(username)
  await page.locator('[data-test="password"]').fill(password)
  await Promise.all([
    page.waitForURL('**/dashboard', { timeout: 20000 }),
    page.getByRole('button', { name: '登录', exact: true }).click(),
  ])
  await page.locator('h1#dashboard-title').waitFor()
  const navigationLabels = ['学术投稿助手', '稿件', '作者', '授权', '期刊', '退出登录', '工作台']
  if (actor === 'admin' || actor === 'auditor') navigationLabels.push('审计日志')
  await assertChineseLabels(page, navigationLabels, `${actor} main navigation`)
  return page
}

async function openManuscript(page) {
  await page.goto(`${base}/manuscripts/${fixture.manuscript_id}`)
  await page.locator('h1#manuscript-detail-title').waitFor()
  await page.locator('[data-test="current-files"] table').waitFor()
  await page.waitForFunction(() => !document.body.innerText.includes('正在加载稿件工作区…'))
}

async function uploadResponse(page) {
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && /\/api\/v1\/manuscripts\/[^/]+\/versions\/[^/]+\/files$/.test(publicPath(response.url())),
  )
  await page.getByRole('button', { name: '上传文件', exact: true }).click()
  return responsePromise
}

;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--no-sandbox'],
  })
  const result = {}
  try {
    const operatorContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
    const operator = await login(operatorContext, fixture.operator_username, process.env.OPERATOR_PASSWORD, 'operator')
    await openManuscript(operator)

    const manuscriptEntry = business.find((entry) => entry.actor === 'operator' && entry.method === 'GET' && entry.path === `/api/v1/manuscripts/${fixture.manuscript_id}`)
    assert(manuscriptEntry, 'manuscript Network response missing')
    const manuscriptBody = await manuscriptEntry.body
    assert.equal(manuscriptBody.json.authors.length, 2)
    manuscriptBody.json.authors.forEach((author) => assert.deepEqual(Object.keys(author).sort(), minimalFields))

    const versionEntry = business.find((entry) => entry.actor === 'operator' && entry.method === 'GET' && entry.path === `/api/v1/manuscripts/${fixture.manuscript_id}/versions/${fixture.version_id}`)
    assert(versionEntry, 'immutable version Network response missing')
    const versionBody = await versionEntry.body
    versionBody.json.metadata_snapshot.authors.forEach((author) => assert.deepEqual(Object.keys(author).sort(), minimalFields))

    const fileListEntry = business.find((entry) => entry.actor === 'operator' && entry.method === 'GET' && entry.path.endsWith(`/versions/${fixture.version_id}/files`))
    assert(fileListEntry, 'file-list Network response missing')
    const fileListBody = await fileListEntry.body
    assert(fileListBody.json.items.length >= 1)
    fileListBody.json.items.forEach((file) => {
      assert(!Object.hasOwn(file, 'storage_path'))
      assert(!Object.hasOwn(file, 'stored_filename'))
    })
    const initialText = await operator.locator('body').innerText()
    await assertChineseLabels(operator, ['工作元数据', '作者名单及顺序', '当前版本文件', '上传文件'], 'manuscript workspace')
    privateValues.forEach((marker) => assert(!initialText.includes(marker), `private marker rendered: ${marker}`))
    assert(!initialText.includes('storage_path'))
    assert(!initialText.includes('stored_filename'))
    await operator.screenshot({ path: path.join(evidence, 'browser-manuscript.png'), fullPage: true })
    result.coauthor_minimal_fields = true
    result.initial_visual_and_dom_check = true

    await operator.locator('[data-test="display-name"]').fill('Browser second family')
    await operator.locator('[data-test="file-input"]').setInputFiles(process.env.PDF_FIXTURE)
    const newFamilyResponse = await uploadResponse(operator)
    assert.equal(newFamilyResponse.status(), 201, await newFamilyResponse.text())
    const newFamilyBody = await newFamilyResponse.json()
    assert.equal(newFamilyBody.file_version, 1)
    await operator.getByRole('status').filter({ hasText: '文件版本为 1' }).waitFor()
    await operator.waitForFunction(() => document.querySelector('[data-test="current-files"]').innerText.includes('Browser second family'))
    result.new_family_upload = { status: 201, file_version: 1 }

    await operator.locator('[data-test="existing-family-mode"]').check()
    await operator.locator('[data-test="file-family"]').selectOption(fixture.file_family_id)
    await operator.locator('[data-test="file-input"]').setInputFiles({ name: 'browser-existing-v2.pdf', mimeType: 'application/pdf', buffer: secondPdf })
    const existingResponse = await uploadResponse(operator)
    assert.equal(existingResponse.status(), 201, await existingResponse.text())
    const existingBody = await existingResponse.json()
    assert.equal(existingBody.file_family_id, fixture.file_family_id)
    assert.equal(existingBody.file_version, 2)
    await operator.getByRole('status').filter({ hasText: '文件版本为 2' }).waitFor()
    await operator.locator(`[data-test="download-${existingBody.id}"]`).waitFor()
    result.existing_family_upload = { status: 201, file_version: 2, file_family_matches: true }

    const downloadEvent = operator.waitForEvent('download')
    const downloadResponseEvent = operator.waitForResponse((response) => publicPath(response.url()).endsWith(`/api/v1/files/${existingBody.id}/download`))
    await operator.locator(`[data-test="download-${existingBody.id}"]`).click()
    const [download, downloadResponse] = await Promise.all([downloadEvent, downloadResponseEvent])
    assert.equal(downloadResponse.status(), 200)
    const downloadedPath = path.join(evidence, 'browser-authorized-download.pdf')
    await download.saveAs(downloadedPath)
    const downloadedHash = crypto.createHash('sha256').update(fs.readFileSync(downloadedPath)).digest('hex')
    assert.equal(downloadedHash, crypto.createHash('sha256').update(secondPdf).digest('hex'))
    result.authorized_download = { status: 200, sha256: downloadedHash }

    const stale = await operatorContext.newPage()
    capturePage('stale', stale)
    staleStarted = performance.now()
    staleMark('stale_tab_opened')
    await openManuscript(stale)
    staleMark('stale_version_2_loaded')
    await operator.locator('[data-test="version-label"]').fill('Browser stale cutoff')
    const versionCreateResponse = operator.waitForResponse((response) =>
      response.request().method() === 'POST' && publicPath(response.url()) === `/api/v1/manuscripts/${fixture.manuscript_id}/versions`,
    )
    await operator.getByRole('button', { name: '创建新稿件版本', exact: true }).click()
    const competingVersion = await versionCreateResponse
    assert.equal(competingVersion.status(), 201)
    await operator.waitForFunction(() => document.body.innerText.includes('当前版本：3'))
    staleMark('competing_version_3_created', { status: competingVersion.status() })

    await stale.locator('[data-test="display-name"]').fill('Stale upload must not commit')
    await stale.locator('[data-test="file-input"]').setInputFiles(process.env.PDF_FIXTURE)
    staleMark('retry_watch_started')
    const conflictResponse = await uploadResponse(stale)
    assert.equal(conflictResponse.status(), 409)
    const conflictBody = await conflictResponse.json()
    assert.equal(conflictBody.code, 'INVALID_MANUSCRIPT_STATE')
    await stale.getByRole('alert').filter({ hasText: '本次上传未自动重试。' }).waitFor()
    await stale.getByRole('button', { name: '刷新稿件及当前版本', exact: true }).waitFor()
    staleMark('non_retry_warning_and_refresh_visible')
    await stale.waitForTimeout(1000)
    const stalePosts = events.filter((entry) => entry.event === 'request' && entry.actor === 'stale' && entry.method === 'POST' && /\/api\/v1\/manuscripts\/[^/]+\/versions\/[^/]+\/files$/.test(entry.path)).length
    assert.equal(stalePosts, 1)
    staleMark('retry_watch_finished', { upload_post_count: stalePosts })
    await stale.screenshot({ path: path.join(evidence, 'browser-stale-409.png'), fullPage: true })
    result.stale_version_conflict = { status: 409, upload_post_count: stalePosts, code: conflictBody.code, retry_watch_ms: 1000 }

    const dashboardResponseEvent = operator.waitForResponse((response) => publicPath(response.url()) === '/api/v1/dashboard/summary')
    await operator.goto(`${base}/audit`)
    await operator.waitForURL('**/dashboard')
    const dashboardResponse = await dashboardResponseEvent
    assert.equal(dashboardResponse.status(), 200)
    await operator.locator('h1#dashboard-title').waitFor()
    await operator.locator('[data-test="author-count"]').waitFor()
    assert.equal(await operator.locator('[data-test="author-count"]').innerText(), '1')
    await assertChineseLabels(operator, ['已授权作者', '当前版本文件', '即将到期的授权', '您的近期操作', '进入稿件工作区'], 'operator dashboard')
    const operatorAuditRequests = events.filter((entry) => entry.event === 'request' && entry.actor === 'operator' && entry.path.startsWith('/api/v1/audit-logs'))
    assert.equal(operatorAuditRequests.length, 0)
    await operator.screenshot({ path: path.join(evidence, 'browser-dashboard-operator.png'), fullPage: true })
    result.operator_dashboard_and_audit_guard = { dashboard_status: dashboardResponse.status(), authorized_author_count: 1, audit_requests: 0 }

    const networkScan = await scanNetwork()
    const scannedSequences = networkScan.scanned
    result.business_network_response_count = business.filter((entry) => entry.actor === 'operator').length
    assert.equal(scannedSequences.length, result.business_network_response_count)
    result.network_sensitive_fields_and_storage_paths_absent = true
    await operatorContext.close()

    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const admin = await login(adminContext, fixture.admin_username, process.env.ADMIN_PASSWORD, 'admin')
    const adminAuditResponse = admin.waitForResponse((response) => publicPath(response.url()) === '/api/v1/audit-logs')
    await admin.goto(`${base}/audit`)
    assert.equal((await adminAuditResponse).status(), 200)
    await admin.locator('h1#audit-list-title').waitFor()
    await admin.locator('tbody tr').first().waitFor()
    await assertChineseAuditTable(admin, 'admin audit')
    await admin.screenshot({ path: path.join(evidence, 'browser-audit-admin.png'), fullPage: true })
    result.admin_audit = { status: 200, rows_visible: true }
    await adminContext.close()

    const auditorContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const auditor = await login(auditorContext, fixture.auditor_username, process.env.AUDITOR_PASSWORD, 'auditor')
    const deniedDashboard = auditor.waitForResponse((response) => publicPath(response.url()) === '/api/v1/dashboard/summary')
    await auditor.goto(`${base}/dashboard`)
    assert.equal((await deniedDashboard).status(), 403)
    await auditor.getByText('无法加载工作台。', { exact: false }).waitFor()
    const auditorAuditResponse = auditor.waitForResponse((response) => publicPath(response.url()) === '/api/v1/audit-logs')
    await auditor.goto(`${base}/audit`)
    assert.equal((await auditorAuditResponse).status(), 200)
    await auditor.locator('tbody tr').first().waitFor()
    await assertChineseAuditTable(auditor, 'auditor audit')
    await auditor.screenshot({ path: path.join(evidence, 'browser-audit-auditor.png'), fullPage: true })
    result.auditor_roles = { dashboard_status: 403, audit_status: 200, rows_visible: true }
    await auditorContext.close()

    result.chinese_ui = true
    result.chinese_ui_scopes = ['main_navigation', 'manuscript_workspace', 'operator_dashboard', 'admin_audit_table', 'auditor_audit_table']
    result.browser = `Google Chrome ${browser.version()} via temporary playwright-core`
    result.headless = true
    result.status = 'passed'
    const networkEvidence = {
      schema_version: 1,
      captured_at: new Date().toISOString(),
      redaction: 'Only API methods, URL paths, statuses, and sequence numbers are retained. No origins, query strings, headers, cookies, CSRF/session tokens, request/response bodies, passwords, or credentials are retained.',
      synthetic_data_only: true,
      events,
      inspected_field_allowlists: [
        {
          response_sequence: manuscriptEntry.sequence,
          json_path: 'authors[]',
          allowlist: minimalFields,
          observed: manuscriptBody.json.authors.map((author) => Object.keys(author).sort()),
          passed: true,
        },
        {
          response_sequence: versionEntry.sequence,
          json_path: 'metadata_snapshot.authors[]',
          allowlist: minimalFields,
          observed: versionBody.json.metadata_snapshot.authors.map((author) => Object.keys(author).sort()),
          passed: true,
        },
      ],
      network_scan: {
        response_sequences: scannedSequences,
        response_count: scannedSequences.length,
        json_response_count: scannedSequences.length - networkScan.nonJson.length,
        non_json_response_sequences: networkScan.nonJson,
        forbidden_synthetic_marker_classes: ['owner_notes', 'owner_email', 'owner_phone', 'coauthor_notes', 'coauthor_email', 'coauthor_phone'],
        forbidden_field_names: ['storage_path', 'stored_filename'],
        passed: true,
      },
      stale_upload_timeline: staleTimeline,
      operator_audit_request_sequences: operatorAuditRequests.map((entry) => entry.sequence),
      authorized_download_sha256: downloadedHash,
      status: 'passed',
    }
    fs.writeFileSync(path.join(evidence, 'browser-network.json'), JSON.stringify(networkEvidence, null, 2) + '\n')
    fs.writeFileSync(path.join(evidence, 'browser-result.json'), JSON.stringify(result, null, 2) + '\n')
    console.log(JSON.stringify(result, null, 2))
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
