export function expectSaveSuccessToast(): void {
  const found = Array.from(document.body.querySelectorAll('.el-message--success'))
    .some((toast) => toast.textContent?.includes('保存成功'))
  expect(found).toBe(true)
}
