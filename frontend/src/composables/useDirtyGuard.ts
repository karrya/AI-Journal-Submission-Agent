import { computed, ref, watch } from 'vue'

export function useDirtyGuard<T>(source: () => T) {
  const baseline = ref(JSON.stringify(source()))
  const dirty = ref(false)

  function refresh(): void {
    dirty.value = JSON.stringify(source()) !== baseline.value
  }

  function capture(): void {
    baseline.value = JSON.stringify(source())
    dirty.value = false
  }

  watch(source, refresh, { deep: true })

  return { dirty: computed(() => dirty.value), capture, refresh }
}
