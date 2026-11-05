import { mount } from '@vue/test-utils'
import AuthorForm from './AuthorForm.vue'
import type { AuthorResponse } from '../api/authors'

const author: AuthorResponse = {
  id: 'a1',
  display_name: 'Existing Author',
  alternate_names: [],
  status: 'active',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}

describe('AuthorForm', () => {
  it('requires identity confirmation before submit', async () => {
    const wrapper = mount(AuthorForm)
    await wrapper.get('[data-test="display-name"]').setValue('张三')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ confirm_identity_change: true })
  })

  it('omits every absent response field from a minimal-response unrelated edit', async () => {
    const wrapper = mount(AuthorForm, { props: { author } })
    await wrapper.get('select').setValue('inactive')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({
      display_name: 'Existing Author',
      status: 'inactive',
      confirm_identity_change: true,
    })
    expect(wrapper.findAll('label').map((label) => label.text())).not.toContain('名')
    expect(wrapper.text()).not.toContain('ORCID')
    expect(wrapper.text()).not.toContain('备注')
    expect(wrapper.text()).not.toContain('电话号码')
  })

  it('requires a nonblank display name even when confirmed', async () => {
    const wrapper = mount(AuthorForm)
    await wrapper.get('[data-test="display-name"]').setValue('   ')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请填写显示姓名')
  })
})
