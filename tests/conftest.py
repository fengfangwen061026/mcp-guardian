# tests/stress/conftest.py
"""
压力测试专用 conftest
- 注册 @pytest.mark.stress 标记（避免 PytestUnknownMarkWarning）
- asyncio 模式设为 auto（pytest-asyncio >= 0.21）
- 超时默认 30s
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "stress: 压力测试，可能耗时较长")
    config.addinivalue_line("markers", "benchmark: 性能基准，不作 pass/fail 判断")


# pytest-asyncio 自动模式（pytest.ini 或 pyproject.toml 里也可以配置）
# 如果版本 < 0.21，改为在 pytest.ini 设置 asyncio_mode = auto
def pytest_collection_modifyitems(items):
    for item in items:
        if "asyncio" in item.keywords or hasattr(item, "get_closest_marker"):
            pass
