// 仅转换界面显示文本，底层枚举值和接口字段保持不变。
export const ROLE_LABELS: Readonly<Record<string, string>> = {
  system_admin: '系统管理员',
  submission_operator: '投稿操作员',
  reviewer: '审稿人',
  author: '作者',
  auditor: '审计员',
}

export const PERMISSION_LABELS: Readonly<Record<string, string>> = {
  'manuscript:read': '查看稿件',
  'manuscript:create': '创建稿件',
  'manuscript:update': '更新稿件',
  'manuscript:file:manage': '管理稿件文件',
  'author:profile:read': '查看作者资料',
  'author:email:read': '查看作者邮箱',
  'author:phone:read': '查看作者电话',
  'author:address:read': '查看作者地址',
  'author:profile:update': '更新作者资料',
}

export const AUTHOR_STATUS_LABELS: Readonly<Record<string, string>> = {
  active: '启用',
  inactive: '停用',
}

export const MANUSCRIPT_STATUS_LABELS: Readonly<Record<string, string>> = {
  draft: '草稿',
  active: '进行中',
  archived: '已归档',
}

export const AUTHORIZATION_STATUS_LABELS: Readonly<Record<string, string>> = {
  not_yet_active: '尚未生效',
  active: '生效中',
  expired: '已过期',
  revoked: '已撤销',
  inactive_subject: '授权对象已停用',
}

export const EMAIL_PURPOSE_LABELS: Readonly<Record<string, string>> = {
  communication: '通讯',
  registration: '注册',
  backup: '备用',
}

export const EMAIL_VERIFICATION_LABELS: Readonly<Record<string, string>> = {
  unverified: '未验证',
  verified: '已验证',
}

export const EMAIL_AUTHORIZATION_LABELS: Readonly<Record<string, string>> = {
  unconfirmed: '未确认',
  authorized: '已授权',
  revoked: '已撤销',
}

export const FILE_TYPE_LABELS: Readonly<Record<string, string>> = {
  main_manuscript: '稿件正文',
  title_page: '标题页',
  abstract: '摘要',
  figure: '图',
  table: '表',
  supplement: '补充材料',
  cover_letter: '投稿信',
  reviewer_suggestion: '审稿人建议',
  other: '其他',
}

export const FILE_INTEGRITY_LABELS: Readonly<Record<string, string>> = {
  normal: '正常',
  missing: '文件缺失',
  hash_mismatch: '哈希不匹配',
}

export const FILE_SCAN_LABELS: Readonly<Record<string, string>> = {
  not_scanned: '未扫描',
  pending: '待扫描',
  scanning: '扫描中',
  clean: '未检出威胁',
  infected: '已检出威胁',
  quarantined: '已隔离',
  failed: '扫描失败',
}

export const AUDIT_CATEGORY_LABELS: Readonly<Record<string, string>> = {
  authentication: '身份认证',
  authorization: '授权',
  business: '业务操作',
  sensitive_access: '敏感访问',
}

export const AUDIT_RESULT_LABELS: Readonly<Record<string, string>> = {
  success: '成功',
  failure: '失败',
}

export const AUDIT_ACTOR_LABELS: Readonly<Record<string, string>> = {
  user: '用户',
  system: '系统',
  anonymous: '匿名用户',
}

export const AUDIT_TARGET_LABELS: Readonly<Record<string, string>> = {
  user: '用户',
  author: '作者',
  author_email: '作者邮箱',
  institution: '机构',
  author_institution: '作者机构关联',
  author_authorization: '作者授权',
  manuscript: '稿件',
  manuscript_version: '稿件版本',
  manuscript_file: '稿件文件',
  publisher: '出版商',
  journal_platform: '期刊平台',
  journal: '期刊',
}

export const PLATFORM_STATUS_LABELS: Readonly<Record<string, string>> = {
  active: '启用',
  needs_review: '待审核',
  disabled: '已停用',
}

export const RESOURCE_KIND_LABELS: Readonly<Record<string, string>> = {
  publisher: '出版商',
  platform: '平台',
  journal: '期刊',
}

export function displayText(labels: Readonly<Record<string, string>>, value: string): string {
  return labels[value] ?? value
}
