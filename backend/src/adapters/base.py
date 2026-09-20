"""外部服务只暴露稳定错误码，不携带原始请求或供应商响应。"""

import logging
import re


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


# httpx 的 INFO 日志在返回响应时包含 URL；高德 Key 位于 query，需在日志产生处脱敏。
# 只修改含 key 参数的日志，不依赖当前 root logger 的级别或处理器设置。


class QueryKeyRedactor(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = re.sub(r"([?&]key=)[^&\s\"\'<>]+", r"\1[REDACTED]", message, flags=re.I)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


_httpx_logger = logging.getLogger("httpx")
if not any(isinstance(f, QueryKeyRedactor) for f in _httpx_logger.filters):
    _httpx_logger.addFilter(QueryKeyRedactor())
