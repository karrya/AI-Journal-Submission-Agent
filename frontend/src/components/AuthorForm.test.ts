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

  it('uses an update payload without inventing absent response fields', async () => {
    const wrapper = mount(AuthorForm, { props: { author } })
    await wrapper.get('[data-test="display-name"]').setValue('Updated Author')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    const payload = wrapper.emitted('submit')?.[0]?.[0] as Record<string, unknown>
    expect(payload).toMatchObject({
      display_name: 'Updated Author',
      confirm_identity_change: true,
    })
    expect(payload).not.toHaveProperty('id')
    expect(payload).not.toHaveProperty('created_at')
    expect(payload).not.toHaveProperty('updated_at')
    expect(payload).not.toHaveProperty('phone_country_code')
    expect(payload).not.toHaveProperty('phone_number')
    expect(wrapper.text()).not.toContain('Phone country code')
    expect(wrapper.text()).not.toContain('Phone number')
    expect(wrapper.text()).not.toContain('undefined')
  })

  it('requires a nonblank display name even when confirmed', async () => {
    const wrapper = mount(AuthorForm)
    await wrapper.get('[data-test="display-name"]').setValue('   ')
    await wrapper.get('[data-test="identity-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('Display name is required')
  })
})
