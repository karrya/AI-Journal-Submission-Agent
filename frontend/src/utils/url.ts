export function safeResourceUrl(value: string | null | undefined): string | null {
  const candidate = value?.trim()
  if (!candidate) return null
  try {
    const url = new URL(candidate)
    const isHttps = url.protocol === 'https:'
    const isApprovedLocalHttp = url.protocol === 'http:'
      && (url.hostname === '127.0.0.1' || url.hostname === 'localhost')
    if ((!isHttps && !isApprovedLocalHttp) || !url.hostname || url.username || url.password) {
      return null
    }
    return candidate
  } catch {
    return null
  }
}
