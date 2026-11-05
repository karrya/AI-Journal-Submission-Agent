import { mount } from '@vue/test-utils'
import EmailTable from './EmailTable.vue'
import type { EmailResponse } from '../api/authors'

const address = (local: string) => `${local}@example.org`

const email: EmailResponse = {
  id: 'e1',
  author_id: 'a1',
  email: address('author'),
  normalized_email: address('author'),
  purpose: 'communication',
  is_primary: false,
  verification_status: 'unverified',
  authorization_status: 'unconfirmed',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}

describe('EmailTable', () => {
  it('requires explicit binding confirmation when creating an email', async () => {
    const wrapper = mount(EmailTable, { props: { emails: [], canManage: true } })
    await wrapper.get('[data-test="new-email"]').setValue(address('new'))
    await wrapper.get('[data-test="create-email-form"]').trigger('submit')
    expect(wrapper.emitted('create')).toBeUndefined()

    await wrapper.get('[data-test="create-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="create-email-form"]').trigger('submit')
    expect(wrapper.emitted('create')?.[0]?.[0]).toEqual({
      email: address('new'),
      purpose: 'communication',
      is_primary: false,
      confirm_email_binding: true,
    })
  })

  it('requires confirmation again when changing an email address', async () => {
    const wrapper = mount(EmailTable, { props: { emails: [email], canManage: true } })
    await wrapper.get('[data-test="edit-email-e1"]').trigger('click')
    await wrapper.get('[data-test="edit-email-address"]').setValue(address('changed'))
    await wrapper.get('[data-test="edit-email-form"]').trigger('submit')
    expect(wrapper.emitted('update')).toBeUndefined()

    await wrapper.get('[data-test="edit-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="edit-email-form"]').trigger('submit')
    expect(wrapper.emitted('update')?.[0]?.[0]).toMatchObject({
      emailId: 'e1',
      payload: {
        email: address('changed'),
        confirm_email_binding: true,
      },
    })
  })

  it('uses a separate explicit confirmation before unbinding', async () => {
    const wrapper = mount(EmailTable, { props: { emails: [email], canManage: true } })
    await wrapper.get('[data-test="delete-email-e1"]').trigger('click')
    expect(wrapper.emitted('delete')).toBeUndefined()
    await wrapper.get('[data-test="confirm-delete-e1"]').trigger('click')
    expect(wrapper.emitted('delete')).toBeUndefined()

    await wrapper.get('[data-test="delete-email-confirm"]').setValue(true)
    await wrapper.get('[data-test="confirm-delete-e1"]').trigger('click')
    expect(wrapper.emitted('delete')?.[0]?.[0]).toEqual({
      emailId: 'e1',
      confirm_email_binding: true,
    })
  })

  it('resets edit and unbind panels when manage permission is lost', async () => {
    const wrapper = mount(EmailTable, { props: { emails: [email], canManage: true } })
    await wrapper.get('[data-test="edit-email-e1"]').trigger('click')
    expect(wrapper.find('[data-test="edit-email-form"]').exists()).toBe(true)

    await wrapper.setProps({ canManage: false })
    expect(wrapper.find('[data-test="edit-email-form"]').exists()).toBe(false)

    await wrapper.setProps({ canManage: true })
    await wrapper.get('[data-test="delete-email-e1"]').trigger('click')
    expect(wrapper.find('[data-test="delete-email-confirm"]').exists()).toBe(true)
    await wrapper.setProps({ canManage: false })
    expect(wrapper.find('[data-test="delete-email-confirm"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="create-email-form"]').exists()).toBe(false)
  })
})
