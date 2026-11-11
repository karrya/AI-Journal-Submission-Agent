import { ElMessage } from 'element-plus'

type JsdomGlobal = typeof globalThis & {
  jsdom?: {
    window: Window & typeof globalThis
  }
}

const dom = (globalThis as JsdomGlobal).jsdom

if (dom) {
  for (const key of ['localStorage', 'sessionStorage'] as const) {
    Object.defineProperty(globalThis, key, {
      configurable: true,
      value: dom.window[key],
    })
  }
}

afterEach(() => {
  vi.useRealTimers()
  ElMessage.closeAll()
  document.querySelectorAll('.el-message').forEach((element) => element.remove())
})
