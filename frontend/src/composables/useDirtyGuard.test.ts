import { nextTick, reactive } from 'vue'
import { useDirtyGuard } from './useDirtyGuard'

describe('useDirtyGuard', () => {
  it('tracks nested form edits and resets the saved baseline', () => {
    const form = reactive({ title: '', authors: [] as string[] })
    const guard = useDirtyGuard(() => form)

    expect(guard.dirty.value).toBe(false)
    form.authors.push('a1')
    guard.refresh()
    expect(guard.dirty.value).toBe(true)
    guard.capture()
    expect(guard.dirty.value).toBe(false)
  })

  it('reacts to deep changes through the watcher', async () => {
    const form = reactive({ profile: { displayName: 'Before' } })
    const guard = useDirtyGuard(() => form)

    form.profile.displayName = 'After'
    await nextTick()

    expect(guard.dirty.value).toBe(true)
  })
})
