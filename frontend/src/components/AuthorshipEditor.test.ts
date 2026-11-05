import { mount } from '@vue/test-utils'
import type { ManuscriptAuthorsUpdate } from '../api/manuscripts'
import AuthorshipEditor from './AuthorshipEditor.vue'

const authors = [
  {
    id: 'a', display_name: 'Owner A', alternate_names: [], status: 'active' as const,
    created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
  },
  {
    id: 'b', display_name: 'Coauthor B', alternate_names: [], status: 'active' as const,
    created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
  },
]

function mountEditor(modelValue = [
  { author_id: 'a', display_name: 'Owner A', position: 1, is_corresponding: true },
]) {
  return mount(AuthorshipEditor, {
    props: { modelValue, ownerAuthorId: 'a', availableAuthors: authors },
  })
}

describe('AuthorshipEditor', () => {
  it('submits ids and positions but never editable display names', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    const payload = wrapper.emitted('submit')?.[0]?.[0] as ManuscriptAuthorsUpdate
    expect(payload.authors[0]).toEqual({ author_id: 'a', position: 1, is_corresponding: true })
    expect(payload.authors[0]).not.toHaveProperty('display_name')
    expect(payload.confirm_authorship_change).toBe(true)
    expect(wrapper.find('[data-test="author-display-name-input"]').exists()).toBe(false)
  })

  it('requires explicit confirmation before emitting an authorship change', async () => {
    const wrapper = mountEditor()
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('保存前请确认作者名单及顺序变更')
  })

  it('adds an authorized coauthor, orders entries, and selects corresponding authors', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-test="new-author"]').setValue('b')
    await wrapper.get('[data-test="add-author"]').trigger('click')
    await wrapper.get('[data-test="move-up-b"]').trigger('click')
    await wrapper.get('[data-test="corresponding-b"]').setValue(true)
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    const payload = wrapper.emitted('submit')?.[0]?.[0] as ManuscriptAuthorsUpdate
    expect(payload.authors).toEqual([
      { author_id: 'b', position: 1, is_corresponding: true },
      { author_id: 'a', position: 2, is_corresponding: true },
    ])
  })

  it('keeps the owner in authorship and requires a corresponding author', async () => {
    const wrapper = mountEditor()
    expect(wrapper.find('[data-test="remove-a"]').exists()).toBe(false)
    await wrapper.get('[data-test="corresponding-a"]').setValue(false)
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请至少选择一位通讯作者')
  })

  it('resets confirmation when the parent supplies a new authorship state', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-test="authorship-confirm"]').setValue(true)
    await wrapper.setProps({
      modelValue: [
        { author_id: 'b', display_name: 'Coauthor B', position: 1, is_corresponding: true },
        { author_id: 'a', display_name: 'Owner A', position: 2, is_corresponding: false },
      ],
    })
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('保存前请确认作者名单及顺序变更')
  })
})
