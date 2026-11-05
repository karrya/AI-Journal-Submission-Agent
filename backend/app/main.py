import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import (
    audit,
    auth,
    authorizations,
    authors,
    dashboard,
    files,
    journals,
    manuscripts,
    readiness,
)
from app.api.v1.deps import first_password_gate, get_request_id
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.auth import LoginRateLimiter

logger = logging.getLogger(__name__)

_OPENAPI_SUMMARIES = {
    "health": "服务健康检查",
    "readiness": "数据库就绪检查",
    "login": "用户登录",
    "logout": "用户退出登录",
    "me": "获取当前用户",
    "get_csrf": "获取 CSRF（跨站请求伪造）防护令牌",
    "change_password": "修改密码",
    "list_authors": "获取作者列表",
    "create_author": "创建作者",
    "get_author": "获取作者详情",
    "update_author": "更新作者",
    "delete_author": "删除作者",
    "list_emails": "获取作者邮箱列表",
    "create_email": "添加作者邮箱",
    "update_email": "更新作者邮箱",
    "delete_email": "删除作者邮箱",
    "list_institutions": "获取机构列表",
    "create_institution": "创建机构",
    "get_institution": "获取机构详情",
    "update_institution": "更新机构",
    "delete_institution": "删除机构",
    "list_author_institutions": "获取作者机构关联列表",
    "create_author_institution": "创建作者机构关联",
    "update_author_institution": "更新作者机构关联",
    "delete_author_institution": "删除作者机构关联",
    "list_authorizations": "获取作者授权列表",
    "create_authorization": "创建作者授权",
    "get_authorization": "获取作者授权详情",
    "update_authorization": "更新作者授权",
    "revoke_authorization": "撤销作者授权",
    "list_manuscripts": "获取稿件列表",
    "create_manuscript": "创建稿件",
    "get_manuscript": "获取稿件详情",
    "update_manuscript": "更新稿件",
    "delete_manuscript": "删除稿件",
    "list_manuscript_authors": "获取稿件署名作者",
    "replace_manuscript_authors": "替换稿件署名作者",
    "list_manuscript_versions": "获取稿件版本列表",
    "create_manuscript_version": "创建稿件版本",
    "get_manuscript_version": "获取稿件版本详情",
    "list_files": "获取稿件版本文件列表",
    "upload_file": "上传稿件文件",
    "get_file": "获取文件元数据",
    "download_file": "下载文件",
    "delete_file": "删除文件",
    "list_publishers": "获取出版商列表",
    "create_publisher": "创建出版商",
    "get_publisher": "获取出版商详情",
    "update_publisher": "更新出版商",
    "delete_publisher": "删除出版商",
    "list_platforms": "获取期刊平台列表",
    "create_platform": "创建期刊平台",
    "get_platform": "获取期刊平台详情",
    "update_platform": "更新期刊平台",
    "delete_platform": "删除期刊平台",
    "list_journals": "获取期刊列表",
    "create_journal": "创建期刊",
    "get_journal": "获取期刊详情",
    "update_journal": "更新期刊",
    "delete_journal": "删除期刊",
    "dashboard_summary": "获取仪表盘摘要",
    "list_audit_logs": "获取审计日志列表",
    "get_audit_log": "获取审计日志详情",
}
_OPENAPI_TAGS = (
    {"name": "authentication", "description": "用户身份认证、会话和密码管理。"},
    {"name": "authors", "description": "作者资料、邮箱和机构关联管理。"},
    {"name": "manuscripts", "description": "稿件元数据、署名作者和版本管理。"},
    {"name": "files", "description": "稿件文件上传、下载和完整性管理。"},
    {"name": "authorizations", "description": "作者数据访问授权管理。"},
    {"name": "journals", "description": "出版商、期刊平台和期刊资料管理。"},
    {"name": "dashboard", "description": "个人仪表盘统计与近期操作。"},
    {"name": "audit", "description": "操作审计日志查询。"},
    {"name": "health", "description": "服务健康与数据库就绪检查。"},
)
_OPENAPI_FIELD_TITLES = {
    "Origin": "请求来源",
    "X-CSRF-Token": "CSRF 防护令牌",
    "absolute_expires_at": "绝对过期时间",
    "abstract": "摘要",
    "action": "操作",
    "actor_type": "操作者类型",
    "actor_user_id": "操作用户 ID",
    "address_line1": "地址行 1",
    "address_line2": "地址行 2",
    "after_summary": "变更后摘要",
    "alternate_names": "别名列表",
    "article_type": "文章类型",
    "article_types": "文章类型列表",
    "author_count": "作者数量",
    "author_guidelines_url": "作者指南 URL",
    "author_id": "作者 ID",
    "authorization_id": "授权 ID",
    "authorization_status": "授权状态",
    "authors": "作者列表",
    "before_summary": "变更前摘要",
    "category": "类别",
    "change_note": "变更说明",
    "city": "城市",
    "code": "代码",
    "confirm_authorship_change": "确认署名变更",
    "confirm_email_binding": "确认邮箱绑定",
    "confirm_identity_change": "确认身份变更",
    "conflict_of_interest_statement": "利益冲突声明",
    "country_code": "国家或地区代码",
    "created_at": "创建时间",
    "created_by": "创建用户 ID",
    "created_from": "创建时间起始",
    "created_to": "创建时间截止",
    "csrf_token": "CSRF 令牌",
    "current_password": "当前密码",
    "current_version_file_count": "当前版本文件数量",
    "current_version_id": "当前版本 ID",
    "data_availability_statement": "数据可用性声明",
    "department": "部门",
    "description": "描述",
    "detail": "详情",
    "display_name": "显示名称",
    "display_order": "显示顺序",
    "eissn": "eISSN（电子国际标准连续出版物号）",
    "email": "邮箱",
    "email_id": "邮箱 ID",
    "error_code": "错误代码",
    "error_message": "错误信息",
    "ethics_statement": "伦理声明",
    "evidence_ref": "证据引用",
    "expiring_authorization_count": "即将到期授权数量",
    "extension": "文件扩展名",
    "family_name": "姓",
    "file": "文件",
    "file_family_id": "文件族 ID",
    "file_id": "文件 ID",
    "file_type": "文件类型",
    "file_version": "文件版本",
    "funding_statement": "资助声明",
    "given_name": "名",
    "id": "资源 ID",
    "idle_expires_at": "空闲会话过期时间",
    "institution_id": "机构 ID",
    "institution_name": "机构名称",
    "institution_type": "机构类型",
    "integrity_status": "完整性状态",
    "internal_number": "内部编号",
    "is_corresponding": "是否通讯作者",
    "is_current": "是否当前机构",
    "is_primary": "是否主要邮箱",
    "issn": "ISSN（国际标准连续出版物号）",
    "items": "记录列表",
    "journal_id": "期刊 ID",
    "key": "键",
    "keywords": "关键词",
    "label": "标签",
    "language": "语言",
    "last_login_at": "最近登录时间",
    "link_id": "关联 ID",
    "loc": "位置",
    "log_id": "日志 ID",
    "manuscript_count": "稿件数量",
    "manuscript_id": "稿件 ID",
    "manuscript_version_id": "稿件版本 ID",
    "metadata_snapshot": "元数据快照",
    "middle_name": "中间名",
    "mime_type": "MIME 类型",
    "msg": "消息",
    "must_change_password": "是否必须修改密码",
    "name": "名称",
    "new_password": "新密码",
    "normalized_email": "规范化邮箱",
    "notes": "备注",
    "orcid": "ORCID（开放研究者与贡献者标识）",
    "order": "排序方向",
    "original_filename": "原始文件名",
    "owner_author_id": "所有者作者 ID",
    "page": "页码",
    "page_size": "每页数量",
    "password": "密码",
    "permission": "权限",
    "permissions": "权限列表",
    "phone_country_code": "电话国家代码",
    "phone_number": "电话号码",
    "platform_id": "平台 ID",
    "position": "署名位置",
    "position_title": "职位名称",
    "postal_code": "邮政编码",
    "publisher_id": "出版商 ID",
    "purpose": "用途",
    "reason": "原因",
    "recent_operations": "近期操作",
    "region": "省、州或地区",
    "request_id": "请求 ID",
    "requirements": "投稿要求",
    "requirements_source_url": "投稿要求来源 URL",
    "requirements_verified_at": "投稿要求核验时间",
    "result": "结果",
    "reviewed_at": "审核时间",
    "reviewed_by": "审核用户 ID",
    "revoked_at": "撤销时间",
    "roles": "角色列表",
    "scan_status": "扫描状态",
    "scope": "适用范围",
    "sha256": "SHA-256 校验值",
    "size_bytes": "文件大小（字节）",
    "sort": "排序字段",
    "source_url": "来源 URL",
    "status": "状态",
    "subject_categories": "学科类别",
    "subject_field": "学科领域",
    "submission_url": "投稿 URL",
    "target_id": "目标 ID",
    "target_type": "目标类型",
    "title": "标题",
    "total": "总记录数",
    "type": "错误类型",
    "updated_at": "更新时间",
    "uploaded_by": "上传用户 ID",
    "user": "用户信息",
    "user_id": "用户 ID",
    "username": "用户名",
    "valid_from": "生效时间",
    "valid_to": "失效时间",
    "validity_status": "有效期状态",
    "value": "值",
    "verification_status": "验证状态",
    "verified_at": "核验时间",
    "version_id": "版本 ID",
    "version_number": "版本号",
    "website_url": "网站 URL",
}
_OPENAPI_COMPONENT_TITLES = {
    "AlternateName": "作者别名",
    "AuditLogResponse": "审计日志响应",
    "AuthorCreate": "作者创建请求",
    "AuthorInstitutionLinkCreate": "作者机构关联创建请求",
    "AuthorInstitutionLinkResponse": "作者机构关联响应",
    "AuthorInstitutionLinkUpdate": "作者机构关联更新请求",
    "AuthorResponse": "作者响应",
    "AuthorUpdate": "作者更新请求",
    "AuthorizationCreate": "授权创建请求",
    "AuthorizationResponse": "授权响应",
    "AuthorizationRevokeRequest": "授权撤销请求",
    "AuthorizationUpdate": "授权更新请求",
    "Body_upload_file_api_v1_manuscripts__manuscript_id__versions__version_id__files_post": "稿件文件上传请求",
    "ChangePasswordRequest": "修改密码请求",
    "CsrfResponse": "CSRF 令牌响应",
    "DashboardSummary": "仪表盘摘要",
    "EmailBindingConfirmation": "邮箱绑定确认",
    "EmailCreate": "邮箱创建请求",
    "EmailResponse": "邮箱响应",
    "EmailUpdate": "邮箱更新请求",
    "FileResponse": "文件响应",
    "HTTPValidationError": "HTTP 请求校验错误",
    "HealthResponse": "健康检查响应",
    "InstitutionCreate": "机构创建请求",
    "InstitutionResponse": "机构响应",
    "InstitutionSummaryResponse": "机构摘要响应",
    "InstitutionUpdate": "机构更新请求",
    "JournalCreate": "期刊创建请求",
    "JournalPlatformCreate": "期刊平台创建请求",
    "JournalPlatformResponse": "期刊平台响应",
    "JournalPlatformUpdate": "期刊平台更新请求",
    "JournalRequirement": "期刊投稿要求",
    "JournalResponse": "期刊响应",
    "JournalUpdate": "期刊更新请求",
    "LoginRequest": "登录请求",
    "LoginResponse": "登录响应",
    "ManuscriptAuthorInput": "稿件署名作者输入",
    "ManuscriptAuthorResponse": "稿件署名作者响应",
    "ManuscriptAuthorsUpdate": "稿件署名作者更新请求",
    "ManuscriptCreate": "稿件创建请求",
    "ManuscriptResponse": "稿件响应",
    "ManuscriptSnapshot": "稿件快照",
    "ManuscriptUpdate": "稿件更新请求",
    "ManuscriptVersionCreate": "稿件版本创建请求",
    "ManuscriptVersionResponse": "稿件版本响应",
    "Page_AuditLogResponse_": "审计日志分页响应",
    "Page_AuthorInstitutionLinkResponse_": "作者机构关联分页响应",
    "Page_AuthorResponse_": "作者分页响应",
    "Page_AuthorizationResponse_": "授权分页响应",
    "Page_EmailResponse_": "邮箱分页响应",
    "Page_FileResponse_": "文件分页响应",
    "Page_InstitutionSummaryResponse_": "机构摘要分页响应",
    "Page_JournalPlatformResponse_": "期刊平台分页响应",
    "Page_JournalResponse_": "期刊分页响应",
    "Page_ManuscriptResponse_": "稿件分页响应",
    "Page_ManuscriptVersionResponse_": "稿件版本分页响应",
    "Page_PublisherResponse_": "出版商分页响应",
    "PublisherCreate": "出版商创建请求",
    "PublisherResponse": "出版商响应",
    "PublisherUpdate": "出版商更新请求",
    "RecentOperation": "近期操作",
    "UserResponse": "用户响应",
    "ValidationError": "校验错误详情",
}
_OPENAPI_RESPONSE_DESCRIPTIONS = {
    "200": "请求成功",
    "201": "创建成功",
    "204": "操作成功，无返回内容",
    "400": "请求格式错误",
    "401": "未通过身份认证",
    "403": "当前用户无权执行此操作",
    "404": "资源不存在",
    "405": "请求方法不受支持",
    "409": "资源状态冲突",
    "413": "文件超过大小限制",
    "415": "文件类型或内容不受支持",
    "422": "请求参数校验失败",
    "429": "请求尝试次数过多",
    "500": "服务器内部错误",
    "503": "数据库暂不可用",
}
_HTTP_ERROR_MESSAGES = {
    "Bad Request": "请求格式错误",
    "Unauthorized": "未通过身份认证",
    "Forbidden": "当前用户无权执行此操作",
    "Not Found": "资源不存在",
    "Method Not Allowed": "请求方法不受支持",
    "Conflict": "资源状态冲突",
    "Request Entity Too Large": "文件超过大小限制",
    "Unsupported Media Type": "文件类型或内容不受支持",
    "Unprocessable Entity": "请求参数校验失败",
    "Too Many Requests": "请求尝试次数过多",
    "Service Unavailable": "数据库暂不可用",
}
_VALIDATION_ERROR_MESSAGES = {
    "missing": "缺少必填字段",
    "extra_forbidden": "不允许额外字段",
    "string_too_short": "字符串长度不足",
    "string_too_long": "字符串长度超限",
    "too_short": "列表或值长度不足",
    "too_long": "列表或值长度超限",
    "greater_than": "数值必须大于下限",
    "greater_than_equal": "数值必须大于或等于下限",
    "less_than": "数值必须小于上限",
    "less_than_equal": "数值必须小于或等于上限",
    "multiple_of": "数值必须符合倍数要求",
    "finite_number": "数值必须是有限值",
    "literal_error": "取值不在允许范围内",
    "enum": "取值不在允许范围内",
    "string_pattern_mismatch": "字符串格式不符合要求",
    "string_type": "必须是字符串",
    "int_type": "必须是整数",
    "int_parsing": "必须是有效整数",
    "int_from_float": "必须是有效整数",
    "float_type": "必须是数值",
    "float_parsing": "必须是有效数值",
    "bool_type": "必须是布尔值",
    "bool_parsing": "必须是有效布尔值",
    "list_type": "必须是列表",
    "dict_type": "必须是对象",
    "none_required": "该字段不能为空",
    "uuid_parsing": "UUID 格式无效",
    "uuid_type": "必须是 UUID",
    "datetime_parsing": "日期时间格式无效",
    "datetime_type": "必须是日期时间",
    "date_parsing": "日期格式无效",
    "date_type": "必须是日期",
    "url_parsing": "URL 格式无效",
    "url_type": "必须是 URL",
    "json_invalid": "JSON 格式无效",
    "json_type": "必须是 JSON 值",
    "model_attributes_type": "必须是对象或模型属性",
    "model_type": "必须是有效模型",
}

app = FastAPI(
    title="学术论文投稿代理",
    description="用于管理作者、稿件、文件、期刊资料和访问授权的本地学术论文投稿代理 API。",
    openapi_tags=list(_OPENAPI_TAGS),
)
app.state.login_rate_limiter = LoginRateLimiter()
app.include_router(readiness.router)
app.include_router(auth.router)
app.include_router(authors.router)
app.include_router(manuscripts.router)
app.include_router(files.router)
app.include_router(authorizations.router)
app.include_router(journals.router)
app.include_router(dashboard.router)
app.include_router(audit.router)


def _contains_chinese(value: str) -> bool:
    return any("一" <= character <= "鿿" for character in value)


def _ensure_chinese_openapi_titles(value, location: str = "document") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            item_location = f"{location}.{key}"
            if key == "title" and isinstance(item, str) and not _contains_chinese(item):
                raise RuntimeError(f"OpenAPI 标题未中文化：{item_location}（{item}）")
            _ensure_chinese_openapi_titles(item, item_location)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_chinese_openapi_titles(item, f"{location}[{index}]")


def custom_openapi():
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        summary = _OPENAPI_SUMMARIES.get(route.name)
        if summary is None:
            continue
        for method in route.methods:
            schema["paths"][route.path][method.lower()]["summary"] = summary
    for operations in schema["paths"].values():
        for operation in operations.values():
            for parameter in operation.get("parameters", []):
                title = _OPENAPI_FIELD_TITLES.get(parameter["name"])
                if title is not None and "schema" in parameter:
                    parameter["schema"]["title"] = title
            for status, response in operation.get("responses", {}).items():
                description = _OPENAPI_RESPONSE_DESCRIPTIONS.get(status)
                if description is not None:
                    response["description"] = description
                for media in response.get("content", {}).values():
                    response_schema = media.get("schema", {})
                    if isinstance(response_schema.get("title"), str):
                        response_schema["title"] = "响应数据"
    for component_name, component_schema in schema["components"]["schemas"].items():
        if "title" in component_schema:
            component_schema["title"] = _OPENAPI_COMPONENT_TITLES[component_name]
        for property_name, property_schema in component_schema.get("properties", {}).items():
            title = _OPENAPI_FIELD_TITLES.get(property_name)
            if title is not None and "title" in property_schema:
                property_schema["title"] = title
    _ensure_chinese_openapi_titles(schema)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]
app.middleware("http")(first_password_gate)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": get_request_id(request),
            "details": exc.details,
        },
    )


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "code": "RESOURCE_NOT_FOUND",
            "message": "资源不存在",
            "request_id": get_request_id(request),
            "details": None,
        },
    )


def _validation_message(error: dict) -> str:
    error_type = str(error.get("type", ""))
    raw_message = str(error.get("msg", ""))
    custom_message = raw_message.removeprefix("Value error, ")
    if custom_message != raw_message and any(
        "一" <= character <= "鿿" for character in custom_message
    ):
        return custom_message
    if error_type == "value_error" and "email address" in raw_message.lower():
        return "邮箱地址格式无效"
    raw_context = error.get("ctx")
    context = raw_context if isinstance(raw_context, dict) else {}
    context_messages = {
        "string_too_short": ("min_length", "字符串长度至少为 {} 个字符"),
        "string_too_long": ("max_length", "字符串长度不能超过 {} 个字符"),
        "too_short": ("min_length", "列表至少包含 {} 项"),
        "too_long": ("max_length", "列表最多包含 {} 项"),
        "greater_than": ("gt", "数值必须大于 {}"),
        "greater_than_equal": ("ge", "数值必须大于或等于 {}"),
        "less_than": ("lt", "数值必须小于 {}"),
        "less_than_equal": ("le", "数值必须小于或等于 {}"),
        "multiple_of": ("multiple_of", "数值必须是 {} 的倍数"),
        "literal_error": ("expected", "取值必须是以下允许值之一：{}"),
        "enum": ("expected", "取值必须是以下允许值之一：{}"),
    }
    constraint = context_messages.get(error_type)
    if constraint is not None:
        context_key, template = constraint
        if context_key in context:
            return template.format(context[context_key])
    return _VALIDATION_ERROR_MESSAGES.get(error_type, "字段值无效")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": list(error["loc"]), "message": _validation_message(error)}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "request_id": get_request_id(request),
            "details": details,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "PERMISSION_DENIED",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "FILE_TOO_LARGE",
        415: "UNSUPPORTED_FILE_TYPE",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_ATTEMPTS",
        503: "DATABASE_UNAVAILABLE",
    }.get(exc.status_code, "HTTP_ERROR")
    detail = str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": code,
            "message": _HTTP_ERROR_MESSAGES.get(detail, detail),
            "request_id": get_request_id(request),
            "details": None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(
        "未处理的请求异常",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": get_request_id(request)},
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误",
            "request_id": get_request_id(request),
            "details": None,
        },
    )
