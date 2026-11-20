# 全站表单与危险操作弹窗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将新增、编辑、删除、撤销、取消、重置密码和文件上传等表单操作统一为 A 方向的居中悬浮弹窗，同时保持现有 API、权限、校验和数据流不变。

**Architecture:** 基于 Element Plus `ElDialog` 封装 `AppModal` 和 `AppConfirmDialog`，共享焦点管理、键盘行为、视觉与移动端规则。`useDirtyGuard` 为页面直接管理的表单提供未保存修改检测；可复用表单组件通过 `dirty-change` 事件把内部 dirty 状态传给父级。

**Tech Stack:** Vue 3.5、TypeScript、Element Plus 2.9、Vitest、Vue Test Utils、Vite。

**Spec:** `docs/superpowers/specs/2026-11-20-modal-forms-design.md`

## Global Constraints

- 不新增依赖，不修改后端 API、数据库、权限、原始请求参数或幂等键。
- 保存失败时弹窗保持打开，输入和请求 ID 不丢失；保存成功后才关闭。
- 遮罩点击不关闭；Esc、取消和标题栏关闭走统一的 dirty guard；提交中禁止关闭。
- 删除、撤销、取消任务必须保留显式确认，执行中禁止重复操作。
- 搜索、筛选、只读详情和证据抽屉保持现状。
- 不自动创建 Git commit，不修改 `scripts/启动说明.md` 和 `aaa.word`。

## Review Focus

- 长表单在弹窗内部滚动，底部操作区始终可用，不能撑破移动端视口。
- 用户修改后关闭弹窗必须二次确认，不能静默丢失输入。
- API 失败后不得关闭弹窗或清空确认状态。
- 嵌套弹窗的焦点、Esc 和 z-index 必须正确，关闭后回到原操作按钮。
- 可复用表单内部状态必须传给 dirty guard，不能仅跟踪父级弹窗开关。

---

### Task 1: 共享弹窗、危险确认与 dirty guard

**Files:**
- Create: `frontend/src/components/AppModal.vue`
- Create: `frontend/src/components/AppConfirmDialog.vue`
- Create: `frontend/src/components/AppModal.test.ts`
- Create: `frontend/src/components/AppConfirmDialog.test.ts`
- Create: `frontend/src/composables/useDirtyGuard.ts`
- Create: `frontend/src/composables/useDirtyGuard.test.ts`
- Modify: `frontend/src/style.css`

**Interfaces:**
- `AppModal` props: `modelValue: boolean`, `title: string`, `description?: string`, `width?: string`, `busy?: boolean`, `dirty?: boolean`, `error?: string`; emits `update:modelValue`, `cancel`。
- `AppConfirmDialog` props: `modelValue: boolean`, `title: string`, `description: string`, `confirmed: boolean`, `confirmationText?: string`, `confirmLabel?: string`, `busy?: boolean`, `error?: string`; emits `update:modelValue`, `update:confirmed`, `confirm`, `cancel`。
- `useDirtyGuard<T>(source: () => T)` returns `{ dirty: ComputedRef<boolean>, capture: () => void, refresh: () => void }`。

- [ ] **Step 1: 写共享组件与 dirty guard 的失败测试**

`AppModal.test.ts` 至少包含：

```ts
it('blocks accidental close when dirty and closes after explicit discard', async () => {
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  const wrapper = mount(AppModal, {
    props: { modelValue: true, title: '编辑期刊', dirty: true },
    slots: { default: '<input data-test="title-input" />' },
    attachTo: document.body,
  })
  await wrapper.get('.el-dialog__close').trigger('click')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  await flushPromises()
  expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  confirm.mockRestore()
})

it('does not close while busy', async () => {
  const wrapper = mount(AppModal, {
    props: { modelValue: true, title: '保存用户', busy: true },
  })
  await wrapper.get('.el-dialog__close').trigger('click')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
```

`AppConfirmDialog.test.ts` 至少包含：

```ts
it('requires explicit confirmation before emitting confirm', async () => {
  const wrapper = mount(AppConfirmDialog, {
    props: { modelValue: true, title: '删除作者', description: '历史记录保留', confirmed: false },
  })
  expect(wrapper.get('[data-test="confirm-danger"]').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ confirmed: true })
  await wrapper.get('[data-test="confirm-danger"]').trigger('click')
  expect(wrapper.emitted('confirm')).toHaveLength(1)
})
```

`useDirtyGuard.test.ts` 至少包含：

```ts
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
```

- [ ] **Step 2: 运行测试并确认因组件不存在而失败**

Run: `npm --prefix frontend test -- --run src/components/AppModal.test.ts src/components/AppConfirmDialog.test.ts src/composables/useDirtyGuard.test.ts`
Expected: FAIL，提示无法解析新增组件或 composable。

- [ ] **Step 3: 实现三个共享模块**

`AppModal.vue` 使用 `ElDialog`，关闭统一走 `requestClose`：

```vue
async function requestClose(): Promise<void> {
  if (props.busy) return
  if (props.dirty) {
    try {
      await ElMessageBox.confirm('关闭后将丢失未保存的修改。', '放弃未保存的修改？', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  emit('update:modelValue', false)
  emit('cancel')
}
```

弹窗必须设置 `:close-on-click-modal="false"`、`:close-on-press-escape="!busy"`、`:show-close="!busy"`，标题使用唯一 id 关联 `aria-labelledby`。`AppConfirmDialog` 仅在 `confirmed && !busy` 时启用危险按钮；关闭时同步重置 `confirmed=false`。

`useDirtyGuard.ts` 使用 JSON 快照跟踪嵌套 reactive 表单：

```ts
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
```

在 `style.css` 增加 `.app-dialog`、`.app-dialog__header`、`.app-dialog__body`、`.app-dialog__footer`、`.app-confirm`、移动端 `@media (max-width: 640px)` 和 `prefers-reduced-motion` 规则。

- [ ] **Step 4: 运行共享模块测试**

Run: `npm --prefix frontend test -- --run src/components/AppModal.test.ts src/components/AppConfirmDialog.test.ts src/composables/useDirtyGuard.test.ts`
Expected: 全部 PASS，无未处理警告。

- [ ] **Step 5: 独立审查共享接口**

检查 props/emits 名称、Teleport 后 DOM 选择器、错误区域和底部插槽；确保后续页面只调用已定义接口。

---

### Task 2: 作者、单位与邮箱表单弹窗化

**Files:**
- Modify: `frontend/src/views/authors/AuthorListView.vue`
- Modify: `frontend/src/views/authors/AuthorDetailView.vue`
- Modify: `frontend/src/components/AuthorForm.vue`
- Modify: `frontend/src/components/InstitutionLinkForm.vue`
- Modify: `frontend/src/components/EmailTable.vue`
- Modify: `frontend/src/views/authors/AuthorListView.test.ts`
- Modify: `frontend/src/views/authors/AuthorDetailView.test.ts`
- Modify: `frontend/src/components/EmailTable.test.ts`

**Interfaces:**
- 可复用表单新增 `dirty-change: [dirty: boolean]` 事件；父级用 `@dirty-change="formDirty = $event"` 驱动 `AppModal.dirty`。
- 邮箱新增按钮使用 `showCreate` 控制；更新、删除和创建成功后分别关闭对应弹窗。

- [ ] **Step 1: 把现有测试改为弹窗行为并运行失败**

新增/修改断言：

```ts
await wrapper.get('[data-test="add-author"]').trigger('click')
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
await wrapper.get('[data-test="display-name"]').setValue('New Author')
await wrapper.get('[data-test="identity-confirm"]').setValue(true)
await wrapper.get('[data-test="author-create-form"]').trigger('submit')
await flushPromises()
expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({ display_name: 'New Author' })
expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
```

邮箱增加失败用例：

```ts
await wrapper.get('[data-test="add-email"]').trigger('click')
await wrapper.get('[data-test="new-email"]').setValue('bad-request@example.com')
await wrapper.get('[data-test="create-email-confirm"]').setValue(true)
await wrapper.get('[data-test="create-email-form"]').trigger('submit')
await flushPromises()
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
expect(wrapper.get('[role="alert"]').text()).toContain('无法创建邮箱绑定')
```

Run: `npm --prefix frontend test -- --run src/views/authors/AuthorListView.test.ts src/views/authors/AuthorDetailView.test.ts src/components/EmailTable.test.ts`
Expected: FAIL，当前仍是内联表单且缺少弹窗和新增邮箱按钮。

- [ ] **Step 2: 用 AppModal/AppConfirmDialog 承载现有表单**

`AuthorListView.vue` 中作者新增：

```vue
<AppModal v-model="showAuthorForm" title="添加作者" description="填写作者身份资料，保存前请逐项核对。" width="720px" :busy="authorBusy" :dirty="authorDirty" :error="authorError">
  <AuthorForm data-test="author-create-form" :submitting="authorBusy" @dirty-change="authorDirty = $event" @submit="saveAuthor" @cancel="showAuthorForm = false" />
</AppModal>
```

删除作者和单位改用：

```vue
<AppConfirmDialog v-model="deletingAuthorId" title="删除作者" description="历史记录将保留，但该资料会从在用列表中移除。" :confirmed="authorDeleteConfirmed" :busy="authorBusy" :error="authorError" @update:confirmed="authorDeleteConfirmed = $event" @confirm="confirmAuthorDelete" />
```

实际实现时增加 `deletingAuthorModel` 计算属性把 `string | null` 转为 boolean，避免把 ID 字符串误当弹窗状态；关闭时置 `null`。

`AuthorForm.vue` 和 `InstitutionLinkForm.vue` 使用 `useDirtyGuard(() => form)`，watch dirty 并发出 `dirty-change`。`EmailTable.vue` 新增 `showCreate`，创建/编辑/解绑分别使用弹窗，保留三个 `confirm_email_binding: true` 请求语义。

- [ ] **Step 3: 运行作者相关测试**

Run: `npm --prefix frontend test -- --run src/views/authors/AuthorListView.test.ts src/views/authors/AuthorDetailView.test.ts src/components/AuthorForm.test.ts src/components/InstitutionLinkForm.test.ts src/components/EmailTable.test.ts`
Expected: 全部 PASS。

---

### Task 3: 作者授权与用户管理弹窗化

**Files:**
- Modify: `frontend/src/views/authors/AuthorizationView.vue`
- Modify: `frontend/src/views/authors/AuthorizationView.test.ts`
- Modify: `frontend/src/views/users/UserListView.vue`
- Modify: `frontend/src/views/users/UserListView.test.ts`

**Interfaces:**
- `AuthorizationView` 使用 `formDirty`、`showForm`、`revokingId`；撤销确认与授权编辑不能同时显示。
- `UserListView` 使用 `showCreate`、`editing`、`resetting` 三个独立弹窗状态，保存成功分别置空。

- [ ] **Step 1: 更新测试验证原 API 参数与失败保留弹窗**

授权撤销断言：

```ts
await wrapper.get(`[data-test="revoke-authorization-${authorization.id}"]`).trigger('click')
await wrapper.get('[data-test="revoke-reason"]').setValue('授权到期调整')
await wrapper.get('[data-test="revoke-confirm"]').setValue(true)
await wrapper.get(`[data-test="confirm-revoke-${authorization.id}"]`).trigger('click')
await flushPromises()
expect(revokeCall?.[0].data).toContain('授权到期调整')
expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
```

用户重置密码失败断言：

```ts
await wrapper.get(`[data-test="reset-user-${user.id}"]`).trigger('click')
await wrapper.get('[data-test="reset-new-password"]').setValue('New-Passphrase-1!')
await wrapper.get('[data-test="reset-password-confirmation"]').setValue('New-Passphrase-1!')
await wrapper.get('[data-test="user-reset-form"]').trigger('submit')
await flushPromises()
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
expect(wrapper.get('[role="alert"]').text()).toContain('无法重置密码')
```

Run: `npm --prefix frontend test -- --run src/views/authors/AuthorizationView.test.ts src/views/users/UserListView.test.ts`
Expected: FAIL，当前表单仍为内联展示。

- [ ] **Step 2: 迁移授权和用户三个表单及撤销确认**

授权表单用 `AppModal`，`useDirtyGuard(() => form)` 计算 dirty；撤销用 `AppConfirmDialog`，原因 textarea 放在默认插槽：

```vue
<AppConfirmDialog v-model="revokeDialogOpen" title="撤销授权" description="撤销将在授权对象的下次请求时生效，且不会删除历史记录。" :confirmed="revokeConfirmed" :busy="saving" :error="errorMessage" confirm-label="确认撤销" @update:confirmed="revokeConfirmed = $event" @confirm="confirmRevoke">
  <label>原因<textarea v-model="revokeReason" data-test="revoke-reason" rows="3" maxlength="2000" /></label>
</AppConfirmDialog>
```

用户新增、编辑、重置密码分别用 `AppModal` 和 `useDirtyGuard(() => createForm)`、`useDirtyGuard(() => editForm)`、`useDirtyGuard(() => resetForm)`；自己重置密码成功后仍按原逻辑清空会话并回登录页。

- [ ] **Step 3: 运行授权与用户测试**

Run: `npm --prefix frontend test -- --run src/views/authors/AuthorizationView.test.ts src/views/users/UserListView.test.ts`
Expected: 全部 PASS。

---

### Task 4: 期刊新增与编辑弹窗化

**Files:**
- Modify: `frontend/src/views/journals/JournalListView.vue`
- Modify: `frontend/src/views/journals/JournalListView.test.ts`

**Interfaces:**
- `showPublisherForm`、`showJournalForm`、`deleteTarget` 驱动三个弹窗；删除仍使用 `deleteConfirmed`。
- `platform_code`、期刊要求、ISSN 校验和 `safeResourceUrl` 行为保持不变。

- [ ] **Step 1: 更新期刊测试验证复杂表单与删除弹窗**

增加断言：

```ts
await wrapper.get('[data-test="add-journal"]').trigger('click')
expect(wrapper.get('[role="dialog"]').text()).toContain('添加期刊')
await wrapper.get('[data-test="journal-platform"]').setValue('OJS')
await wrapper.get('[data-test="journal-form"]').trigger('submit')
await flushPromises()
expect(JSON.parse(String(createCall?.[0].data))).toMatchObject({ platform_code: 'OJS' })
expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
```

删除失败断言：

```ts
await wrapper.get('[data-test="delete-journal-j1"]').trigger('click')
await wrapper.get('[data-test="delete-confirm"]').setValue(true)
await wrapper.get('[data-test="confirm-delete-journal-j1"]').trigger('click')
await flushPromises()
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
expect(wrapper.get('[role="alert"]').text()).toContain('无法删除该资源')
```

Run: `npm --prefix frontend test -- --run src/views/journals/JournalListView.test.ts`
Expected: FAIL，当前没有弹窗且失败路径未覆盖。

- [ ] **Step 2: 迁移出版商、期刊和删除确认**

出版商表单用标准宽度，期刊复杂表单用 `width="960px"`。`useDirtyGuard` 分别跟踪 `publisherForm` 和 `journalForm`，在 `openPublisherForm`、`openJournalForm` 完成后 `capture()` 基线。删除使用 `AppConfirmDialog`，保留 `deleteTarget.kind/id` 和原删除分支。

- [ ] **Step 3: 运行期刊测试**

Run: `npm --prefix frontend test -- --run src/views/journals/JournalListView.test.ts src/views/journals/JournalIdentificationPanel.test.ts`
Expected: 全部 PASS，识别面板不受影响。

---

### Task 5: 稿件、作者名单、版本和文件上传弹窗化

**Files:**
- Modify: `frontend/src/views/manuscripts/ManuscriptListView.vue`
- Modify: `frontend/src/views/manuscripts/ManuscriptListView.test.ts`
- Modify: `frontend/src/views/manuscripts/ManuscriptDetailView.vue`
- Modify: `frontend/src/views/manuscripts/ManuscriptDetailView.test.ts`
- Modify: `frontend/src/components/AuthorshipEditor.vue`
- Modify: `frontend/src/components/AuthorshipEditor.test.ts`
- Modify: `frontend/src/components/FileFamilyUpload.vue`
- Modify: `frontend/src/components/FileFamilyUpload.test.ts`

**Interfaces:**
- `ManuscriptListView` 的 `showCreate` 控制宽弹窗。
- `ManuscriptDetailView` 新增 `showMetadata`、`showAuthorship`、`showVersion`、`showUpload`；非编辑状态继续展示只读元数据和作者名单。
- `AuthorshipEditor` 与 `FileFamilyUpload` 通过 `dirty-change` 暴露内部修改状态。

- [ ] **Step 1: 更新稿件测试验证原快照、作者名单与上传请求**

稿件详情断言：

```ts
await wrapper.get('[data-test="edit-metadata"]').trigger('click')
await wrapper.get('[data-test="metadata-title"]').setValue('Updated manuscript')
await wrapper.get('[data-test="metadata-form"]').trigger('submit')
await flushPromises()
expect(updateCall?.[0].url).toBe(`/manuscripts/${manuscript.id}`)
expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
expect(wrapper.text()).toContain('Updated manuscript')
```

上传失败断言：

```ts
await wrapper.get('[data-test="upload-file"]').trigger('click')
await uploadInput.setValue(file)
await wrapper.get('[data-test="file-upload-form"]').trigger('submit')
await flushPromises()
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
expect(wrapper.get('[role="alert"]').text()).toContain('无法上传')
```

Run: `npm --prefix frontend test -- --run src/views/manuscripts/ManuscriptListView.test.ts src/views/manuscripts/ManuscriptDetailView.test.ts src/components/AuthorshipEditor.test.ts src/components/FileFamilyUpload.test.ts`
Expected: FAIL，当前表单仍为内联展示。

- [ ] **Step 2: 迁移稿件工作区表单**

创建稿件用 `AppModal width="960px"`，保留所有者选择、完整 metadata 和 `AuthorshipEditor`。详情页在只读内容旁增加 `data-test="edit-metadata"`、`data-test="edit-authorship"`、`data-test="create-version"`、`data-test="upload-file"` 按钮，分别打开弹窗。

版本创建使用 `useDirtyGuard(() => ({ label: versionLabel.value, note: versionNote.value }))`；成功后先关闭弹窗，再调用原 `loadWorkspace()`。文件上传仅负责承载表单，文件选择、MIME 校验、哈希和上传顺序不改。

- [ ] **Step 3: 运行稿件相关测试**

Run: `npm --prefix frontend test -- --run src/views/manuscripts/ManuscriptListView.test.ts src/views/manuscripts/ManuscriptDetailView.test.ts src/components/AuthorshipEditor.test.ts src/components/FileFamilyUpload.test.ts`
Expected: 全部 PASS。

---

### Task 6: 注册任务创建与取消弹窗化

**Files:**
- Modify: `frontend/src/views/registration/RegistrationView.vue`
- Modify: `frontend/src/views/registration/RegistrationView.test.ts`

**Interfaces:**
- 新增 `showCreate` 控制目标任务选择弹窗；`cancelTargetId` 控制危险确认弹窗。
- 创建仍复用 `createAttempt` 的签名和幂等键；取消仍要求 `cancelConfirmed`。

- [ ] **Step 1: 更新注册测试验证幂等键和危险确认**

创建断言：

```ts
await wrapper.get('[data-test="open-create-registration"]').trigger('click')
await selectSupportedTarget(wrapper)
await wrapper.get('[data-test="create-registration-task"]').trigger('click')
await flushPromises()
expect(payload).toMatchObject({ author_id: 'a1', publisher_id: 'p1', journal_id: 'j1', platform_code: 'EM' })
expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
```

取消失败断言：

```ts
await wrapper.get('[data-test="cancel-task-t1"]').trigger('click')
await wrapper.get('[data-test="cancel-confirmation"]').setValue(true)
await wrapper.get('[data-test="confirm-cancel-t1"]').trigger('click')
await flushPromises()
expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
expect(wrapper.get('[role="alert"]').text()).toContain('无法取消')
```

Run: `npm --prefix frontend test -- --run src/views/registration/RegistrationView.test.ts`
Expected: FAIL，当前创建与取消仍为内联区域。

- [ ] **Step 2: 迁移注册创建与取消**

创建入口按钮放在任务列表标题区，目标四步选择、只读摘要和创建按钮放入 `AppModal width="960px"`。弹窗关闭不得清空 `createAttempt`，网络失败后的再次提交仍使用相同幂等键；只有明确改变目标签名才生成新键。

取消用 `AppConfirmDialog`，后果文案保留“已产生的平台状态不会被撤销”，确认 checkbox 的 `data-test` 不变。

- [ ] **Step 3: 运行注册测试**

Run: `npm --prefix frontend test -- --run src/views/registration/RegistrationView.test.ts`
Expected: 全部 PASS。

---

### Task 7: 全站残留检查与完整验证

**Files:**
- Modify only files with remaining inline form behavior discovered by the scan.
- No backend changes.

- [ ] **Step 1: 扫描内联表单与旧弹窗符号**

Run: `rg -n 'confirmation-panel|stacked-form|ElDialog|role="dialog"|show[A-Z][A-Za-z]+Form' frontend/src --glob '*.vue'`
Expected: 表单只出现在 `AppModal` 内部、可复用表单组件或明确的只读工作流中；没有遗留 `confirmation-panel`。

- [ ] **Step 2: 运行完整项目验证**

Run: `bash scripts/verify.sh`
Expected: Ruff、mypy、全部后端测试、覆盖率、OpenAPI/Newman、全部前端测试、前端覆盖率和生产构建全部通过。

- [ ] **Step 3: 浏览器验收**

确认前端运行于 `http://127.0.0.1:5173`。至少检查：

- 桌面宽度下期刊编辑长表单、稿件创建和删除确认；
- 移动宽度下按钮换行、弹窗内部滚动、底部操作区可用；
- Esc、取消、dirty 二次确认、失败后弹窗保留；
- 关闭后焦点返回原操作按钮，页面背景不滚动。

- [ ] **Step 4: 最终代码审查与结果报告**

进行只读代码审查，重点检查 dirty guard、API 参数不变、失败路径、嵌套弹窗和可访问性。报告测试数量、构建结果、浏览器检查结果及任何未解决限制；不自动提交 Git。
