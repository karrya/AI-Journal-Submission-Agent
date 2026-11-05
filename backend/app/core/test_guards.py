from pathlib import Path


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_test_environment(
    database_name: str | None,
    test_storage_root: str | Path,
    live_storage_root: str | Path,
    *,
    environment: str | None,
    database_host: str | None,
) -> None:
    """在测试执行迁移或删除数据前拒绝不安全的配置。"""
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError("测试数据库名称必须以 _test 结尾")
    if database_host not in LOOPBACK_HOSTS:
        raise RuntimeError("测试数据库主机必须显式指定为回环地址")
    if environment != "test":
        raise RuntimeError("测试环境必须设置 ENVIRONMENT=test")

    test_storage = Path(test_storage_root).resolve()
    live_storage = Path(live_storage_root).resolve()
    if test_storage == live_storage or live_storage in test_storage.parents:
        raise RuntimeError("测试不得使用正式存储目录")
