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
