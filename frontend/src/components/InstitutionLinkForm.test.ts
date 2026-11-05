import { mount } from '@vue/test-utils'
import InstitutionLinkForm from './InstitutionLinkForm.vue'
import type { InstitutionSummaryResponse } from '../api/authors'

const institutions: InstitutionSummaryResponse[] = [{
  id: 'i1',
  name: 'Example University',
  institution_type: 'university',
  website_url: 'https://university.example',
  country_code: 'CN',
  city: 'Beijing',
}]

describe('InstitutionLinkForm', () => {
  it('uses institution summaries and requires affiliation confirmation', async () => {
    const wrapper = mount(InstitutionLinkForm, { props: { institutions } })
    expect(wrapper.text()).toContain('Example University')
    expect(wrapper.text()).not.toContain('address_line1')
    await wrapper.get('[data-test="institution-select"]').setValue('i1')
    await wrapper.get('[data-test="department"]').setValue('Computer Science')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()

    await wrapper.get('[data-test="affiliation-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      institution_id: 'i1',
      department: 'Computer Science',
      display_order: 0,
    })
    expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('confirm_affiliation_change')
  })

  it('rejects an end date earlier than the start date', async () => {
    const wrapper = mount(InstitutionLinkForm, { props: { institutions } })
    await wrapper.get('[data-test="institution-select"]').setValue('i1')
    await wrapper.get('[data-test="valid-from"]').setValue('2026-11-05')
    await wrapper.get('[data-test="valid-to"]').setValue('2026-11-04')
    await wrapper.get('[data-test="affiliation-confirm"]').setValue(true)
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('结束日期不得早于开始日期')
  })
})
