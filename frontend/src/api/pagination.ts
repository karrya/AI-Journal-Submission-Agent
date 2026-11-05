import type { Page } from './authors'

export async function fetchAllPages<T>(
  requestPage: (page: number, pageSize: number) => Promise<Page<T>>,
): Promise<Page<T>> {
  const pageSize = 100
  const items: T[] = []
  let page = 1
  let total = 0

  while (true) {
    const result = await requestPage(page, pageSize)
    items.push(...result.items)
    total = result.total
    if (items.length >= total) break
    if (result.items.length === 0) {
      throw new Error('Pagination ended before all relationship items were loaded')
    }
    page += 1
  }

  return { items, page: 1, page_size: Math.max(pageSize, items.length), total }
}
