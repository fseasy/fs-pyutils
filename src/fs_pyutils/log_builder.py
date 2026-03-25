from __future__ import annotations

import json
import logging
import socket
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import SysLogHandler

# import traceback
from typing import Any
from urllib.parse import urlparse


@dataclass
class SyslogLogField:
  host: str = "py.app"
  """You can use 1. domain (https?://xxx.xxx) 2. hostname xxx.xxx 3. or some featured tag."""
  tag: str = "py_app"
  """Used as RFC 3164 syslog tag. Will be sanitized. You can use .gen_tag method to generate this one"""

  @classmethod
  def gen_tag(cls, host: str, tag_suffix: str) -> str:
    """Generate tag from host+tag-suffix.
    Args:
      host: the value you put in the SyslogLogField::host
    """
    hostname = _parse_hostname(host)
    tag = f"{hostname}_{tag_suffix}"
    return _sanitize4syslog_tag(tag) or "py_app"


def build_logger(
  name: str,
  level: int,
  syslog_address: tuple[str, int] | None = None,
  syslog_log_field: SyslogLogField | None = None,
) -> logging.Logger:
  """It will build a logger with a naive stream logger and a JSON formatted syslog.
  Args:
    syslog_address: used for syslog (you can setup a grafana alloy), will send a json log
    syslog_log_field: used in log json to signature the log source
  """

  logger = logging.getLogger(name)

  streamHandler = logging.StreamHandler(stream=sys.stderr)
  fmt = SingleLineFormatter("%(asctime)s/%(name)s/%(levelname)s/%(filename)s:%(lineno)d> %(message)s")
  streamHandler.setFormatter(fmt)
  streamHandler.setLevel(level)

  logger.addHandler(streamHandler)
  logger.setLevel(level)

  # syslog
  if syslog_address:
    syslog_log_field = syslog_log_field or SyslogLogField()
    try:
      hostname = _parse_hostname(syslog_log_field.host)
      syslog_handler = NginxAlignedSyslogHandler(
        address=syslog_address, hostname=hostname, tag=syslog_log_field.tag, facility=SysLogHandler.LOG_LOCAL7
      )
      json_fmt = JsonSyslogFormatter(syslog_log_field.host)
      syslog_handler.setFormatter(json_fmt)
      syslog_handler.setLevel(level)
      logger.addHandler(syslog_handler)
    except Exception as e:
      logger.warning(f"Failed to add syslog, err={e}")
  return logger


class SingleLineFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    fmt_line = super().format(record)
    single_line = fmt_line.replace("\n", " ↵ ")
    # naively append extra fields
    extra_kv = _get_extra_kv(record)
    if extra_kv:
      extra_line = json.dumps(extra_kv, ensure_ascii=False, default=str)
      single_line = f"{single_line} extra={extra_line}"
    return single_line


class JsonSyslogFormatter(logging.Formatter):
  """A formatter for syslog in json format"""

  def __init__(self, host: str):
    """init with a hostname"""
    super().__init__(fmt="%(message)s")
    self._host = host.strip()

  def _build_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
    iso_time = datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="seconds")

    log_data = {
      "host": self._host,
      "time": iso_time,  # to align the loki receiver
      "level": record.levelname,
      "logger": record.name,
      "file": f"{record.filename}:{record.lineno}",
      "msg": record.getMessage(),
    }
    if record.exc_info:
      log_data["traceback"] = self.formatException(record.exc_info)

    # add info from extra={...}
    log_data.update(_get_extra_kv(record))
    return log_data

  def format(self, record: logging.LogRecord) -> str:
    log_data = self._build_log_dict(record)
    return json.dumps(log_data, default=str)


class NginxAlignedSyslogHandler(logging.Handler):
  """
  严格遵守 RFC 3164，生成与 Nginx 完全一致的 Syslog UDP 报文。
  解决了 Python SysLogHandler 日期填充错误、格式错位的问题。
  """

  def __init__(self, address: tuple[str, int], hostname: str, tag: str | None = None, facility: int = 23):
    """
    Args:
      - hostname: used in SYSLOG header
      - app_tag: used in SYSLOG header
      - facility: used in SYSLOG header (pri), Nginx may use `Local7 (23)` as default.
    """
    super().__init__()
    self.address = address
    # tags
    self.hostname = hostname or "py.app"  # we assert it has value to avoid break the header
    self.tag = _sanitize4syslog_tag(tag or "py_app") or "py_app"
    self.facility = facility
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

  def emit(self, record: logging.LogRecord) -> None:
    try:
      # 1. 提取 JSON message
      msg = self.format(record).lstrip()  # remove the potential leading space to keep the format

      # 2. 计算 PRI (Facility * 8 + Severity)
      severity_map = {
        logging.DEBUG: 7,
        logging.INFO: 6,
        logging.WARNING: 4,
        logging.ERROR: 3,
        logging.CRITICAL: 2,
      }
      severity = severity_map.get(record.levelno, 6)
      pri = (self.facility * 8) + severity

      # 3. 严格生成 RFC 3164 时间戳: "Mmm dd hh:mm:ss"
      # 注意：个位数日期必须用空格补齐，比如 "Feb  3" 不能是 "Feb 03"
      now = datetime.now()
      month = now.strftime("%b")
      day = now.day
      day_str = f"{day:>2}"  # 右对齐，不足补空格。这一步完美解决解析失败问题！
      time_str = now.strftime("%H:%M:%S")
      timestamp = f"{month} {day_str} {time_str}"

      # 4. 严格拼接，完全复刻 Nginx 格式: <PRI>TIMESTAMP HOSTNAME TAG: MSG
      # 注意 self.tag 后面紧跟冒号和空格 ": "
      syslog_msg = f"<{pri}>{timestamp} {self.hostname} {self.tag}: {msg}\n"

      # 5. 发送 UDP 包
      self.sock.sendto(syslog_msg.encode("utf-8"), self.address)
    except Exception:
      self.handleError(record)


def _get_extra_kv(record: logging.LogRecord) -> dict[str, Any]:
  RESERVED_ATTRS = set(
    (
      "args",
      "asctime",
      "created",
      "exc_info",
      "exc_text",
      "filename",
      "funcName",
      "levelname",
      "levelno",
      "lineno",
      "message",
      "module",
      "msecs",
      "msg",
      "name",
      "pathname",
      "process",
      "processName",
      "relativeCreated",
      "stack_info",
      "thread",
      "threadName",
      "taskName",
    )
  )
  extra_data: dict[str, Any] = {}
  for key, value in record.__dict__.items():
    if key not in RESERVED_ATTRS:
      extra_data[key] = value
  return extra_data


def _parse_hostname(host: str) -> str:
  # 1. is it a domain?
  hostname = urlparse(host if "://" in host else "https://" + host).hostname
  if hostname:
    return hostname
  # not a valid domain, return the raw input
  return host.strip()  # at least remove surrounding space


def _sanitize4syslog_tag(s: str) -> str:
  r"""For safety, replace anything except alphabet&digit&_ to `_`, merge duplicated invalid char"""
  import re

  return re.sub(r"[^a-zA-Z0-9_]+", "_", s).strip("_")
