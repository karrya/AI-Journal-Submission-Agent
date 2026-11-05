const { chromium } = require('playwright-core')
const fs = require('fs')
const path = require('path')
const assert = require('assert/strict')

const base = 'http://127.0.0.1:5173'
const fixture = JSON.parse(fs.readFileSync(process.env.FIXTURE_FILE, 'utf8'))
const evidence = process.env.EVIDENCE_DIR
const events = []

function publicPath(url) {
  return new URL(url).pathname
}

;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--no-sandbox'],
  })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage()
    page.on('request', (request) => {
      const requestPath = publicPath(request.url())
      if (requestPath.startsWith('/api/v1/')) {
        events.push({ event: 'request', method: request.method(), path: requestPath })
      }
    })
    page.on('response', (response) => {
      const responsePath = publicPath(response.url())
      if (responsePath.startsWith('/api/v1/')) {
        events.push({ event: 'response', method: response.request().method(), path: responsePath, status: response.status() })
      }
    })

    await page.goto(`${base}/login`)
    await page.locator('[data-test="username"]').fill(fixture.operator_username)
    await page.locator('[data-test="password"]').fill(process.env.OPERATOR_PASSWORD)
    await Promise.all([
      page.waitForURL('**/dashboard', { timeout: 20000 }),
      page.getByRole('button', { name: '登录', exact: true }).click(),
    ])

    await page.goto(`${base}/manuscripts/${fixture.first_manuscript_id}`)
    await page.locator('h1#manuscript-detail-title').waitFor()
    await page.locator('[data-test="current-files"] table').waitFor()
    assert((await page.locator('body').innerText()).includes(fixture.first_title))
    await page.locator('[data-test="authorship-confirm"]').check()
    await page.evaluate(() => {
      window.staleAuthorshipForm = document.querySelector('[data-test="authorship-form"]')
    })

    let releaseSecond
    const secondGate = new Promise((resolve) => { releaseSecond = resolve })
    let markSecondRequested
    const secondRequested = new Promise((resolve) => { markSecondRequested = resolve })
    await page.route(`**/api/v1/manuscripts/${fixture.second_manuscript_id}`, async (route) => {
      markSecondRequested()
      await secondGate
      await route.continue()
    })
    await page.evaluate((id) => {
      window.history.pushState({}, '', `/manuscripts/${id}`)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, fixture.second_manuscript_id)
    await secondRequested
    await page.getByText('正在加载稿件工作区…', { exact: true }).waitFor()

    const pendingText = await page.locator('body').innerText()
    for (const oldValue of [fixture.first_title, fixture.first_snapshot_title, fixture.first_filename]) {
      assert(!pendingText.includes(oldValue), `old representation remained during m2 load: ${oldValue}`)
    }
    assert.equal(await page.locator('h1#manuscript-detail-title').count(), 0)
    await page.screenshot({ path: path.join(evidence, 'browser-route-reuse-loading.png'), fullPage: true })

    await page.evaluate(() => {
      window.staleAuthorshipForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await page.waitForTimeout(150)
    releaseSecond()
    await page.locator('h1#manuscript-detail-title').waitFor()
    await page.locator('[data-test="current-files"] table').waitFor()
    await page.waitForFunction(() => !document.body.innerText.includes('正在加载稿件工作区…'))

    const finalText = await page.locator('body').innerText()
    assert(finalText.includes(fixture.second_title))
    assert(finalText.includes(fixture.second_snapshot_title))
    assert(finalText.includes(fixture.second_filename))
    for (const oldValue of [fixture.first_title, fixture.first_snapshot_title, fixture.first_filename]) {
      assert(!finalText.includes(oldValue), `old representation remained after m2 load: ${oldValue}`)
    }
    const authorshipPuts = events.filter((entry) => entry.event === 'request' && entry.method === 'PUT' && /\/api\/v1\/manuscripts\/[^/]+\/authors$/.test(entry.path))
    assert.deepEqual(authorshipPuts, [])
    await page.screenshot({ path: path.join(evidence, 'browser-route-reuse-second.png'), fullPage: true })

    const result = {
      schema_version: 1,
      captured_at: new Date().toISOString(),
      browser: `Google Chrome ${browser.version()} via temporary playwright-core`,
      synthetic_data_only: true,
      route_reuse: 'm1 to m2 through Vue Router popstate with delayed m2 GET',
      old_representation_cleared_before_m2_response: true,
      detached_m1_authorship_submit_attempted: true,
      authorship_put_request_count: authorshipPuts.length,
      second_manuscript_rendered: true,
      redaction: 'Only synthetic assertions, API methods, paths, and statuses are retained. No credentials, headers, cookies, bodies, origins, or query strings are retained.',
      events,
      status: 'passed',
    }
    fs.writeFileSync(path.join(evidence, 'browser-route-reuse-result.json'), JSON.stringify(result, null, 2) + '\n')
    console.log(JSON.stringify({ status: result.status, authorship_put_request_count: 0, second_manuscript_rendered: true }))
    await context.close()
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
