import logging
import os
from typing import Any

#! note1: this module must be used in python env where contains the gunicorn (it's reasonable)
from gunicorn.config import Config
from gunicorn.glogging import Logger as GLogger

from .log_builder import JsonSyslogFormatter, NginxAlignedSyslogHandler

#! note2: you must set `SYSLOG_ADDRESS` in ENV, in format `ip:port`, like: "127.0.0.1:5140"
g_syslog_addr_str = os.environ["SYSLOG_ADDRESS"]
#! it's better also set the hostname.
g_hostname = os.getenv("HOSTNAME", "gunicorn-default")


class GunicornSyslogLogger(GLogger):
  def setup(self, cfg: Config) -> None:
    super().setup(cfg)

    ip, port = g_syslog_addr_str.split(":")
    syslog_address = (ip, int(port))

    # 继承 gunicorn 的日志级别 => cfg.loglevel 是 string, 必须得改成 int
    level = self.LOG_LEVELS.get(cfg.loglevel.lower(), logging.INFO)

    # --- 准备你的 Handler 和 Formatter ---
    syslog_handler = NginxAlignedSyslogHandler(
      address=syslog_address,
      hostname=g_hostname,
      facility=23,  # Local7
    )

    # 使用你现有的 JsonSyslogFormatter
    json_fmt = JsonSyslogFormatter(g_hostname)
    syslog_handler.setFormatter(json_fmt)
    syslog_handler.setLevel(level)

    # --- 将 Handler 绑定到 Gunicorn 的两个核心 Logger ---
    # 1. 错误日志 (gunicorn.error) (we dont' remove the default error log handler, just append)
    self.error_log.addHandler(syslog_handler)
    self.error_log.setLevel(level)

    # 2. 访问日志 (gunicorn.access)
    # 移除默认的 access_log handler (防止重复打印到 stdout)
    self.access_log.handlers = []
    self.access_log.addHandler(syslog_handler)
    self.access_log.setLevel(level)
    self.access_log.propagate = False

  def access(self, resp, req, environ, request_time) -> None:  # type: ignore
    """
    这个方法覆盖了 Gunicorn 默认逻辑。
    它把本该塞进 args 的字典，转而塞进 extra。
    这样就能被你现有的 _get_extra_kv 自动识别并转为 JSON 字段。
    """
    atoms = self.atoms(resp, req, environ, request_time)
    # 消息内容可以设为 "access" 或者根据 access_log_format 渲染
    self.access_log.info("access", extra=atoms)


class GunicornJsonFormatter(JsonSyslogFormatter):
  def _build_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
    log_data = super()._build_log_dict(record)

    # mapping key for readability
    mapping = {"h": "remote_ip", "m": "method", "U": "path", "s": "status", "M": "duration_ms", "a": "user_agent"}

    for short_key, long_key in mapping.items():
      if short_key in log_data:
        log_data[long_key] = log_data.pop(short_key)

    return log_data
