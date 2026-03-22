"""Systemd notifier, should be used with fastapi.
1. intercept the gunicorn default `READY` signal (by pop env var: NOTIFY_SOCKET)
2. export a lifespan manager with following features:
   - notify READY/STOPPING
   - db watchdog for systemd.

To enable systemd watchdog:
1. in systemd service. set:
   Type=notify

   WatchdogSec=45(or any other value)
   Restart=always
"""

import asyncio
import logging
import os
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

_CUSTOM_NOTIFY_SOCKET_VAR_NAME = "CUSTOM_NOTIFY_SOCKET"


def intercept_server_ready_signal() -> None:
  """pop NOTIFY_SOCKET from env and set it to our custom var"""
  # 拦截 Systemd 的通知 Socket
  # Gunicorn 内部逻辑是：如果检测到环境变量 NOTIFY_SOCKET，就会在启动后发送 READY=1。
  # 我们在 Gunicorn 初始化前把它移走，存入自定义变量中。
  _real_notify_socket = os.environ.pop("NOTIFY_SOCKET", None)
  if _real_notify_socket:
    # 存入一个 Gunicorn 不认识，但我们代码能找到的变量名
    os.environ[_CUSTOM_NOTIFY_SOCKET_VAR_NAME] = _real_notify_socket


@asynccontextmanager
async def systemd_notifier_lifespan(
  app: FastAPI, async_db_engine: AsyncEngine, logger: logging.Logger | None = None
) -> AsyncGenerator[Any, None]:
  """Please call this after you do anything else! because it'll send `READY/STOPPING` signal"""
  del app
  # 启动看门狗后台任务
  task = asyncio.create_task(_db_watchdog_task(async_db_engine, logger=logger))
  # 发送启动成功
  _send_sd_notify("READY=1", logger=logger)
  try:
    yield
  finally:
    _send_sd_notify("STOPPING=1", logger=logger)

    try:
      task.cancel()
    except asyncio.CancelledError:
      pass  # 预期的取消异常
    if logger:
      logger.info("systemd: db watchdog stopped.")
    _send_sd_notify("STATUS=db watchdog stopped", logger=logger)


async def _db_watchdog_task(async_db_engine: AsyncEngine, logger: logging.Logger | None = None) -> None:
  """后台监控任务：定期执行 SQL 任务，确保 SQL 运行正常，并喂狗"""
  interval_usec = os.getenv("WATCHDOG_USEC")
  if not interval_usec:
    if logger:
      logger.warning("db watchdog isn't set in systemd. skip watchdog task")
    return
  watch_sleep_sec = round(int(interval_usec) / 1_000_000 / 3)  # try to report 3 times in one watch duration
  _send_sd_notify(f"STATUS=prepared to create systemd watchdog task, report interval={watch_sleep_sec}s", logger=logger)
  while True:
    try:
      async with async_db_engine.begin() as conn:
        await conn.exec_driver_sql("SELECT 1")

      # 2. 如果成功执行，说明事件循环没死，DB 没卡死，通知 Systemd
      _send_sd_notify("WATCHDOG=1", logger=logger)
      _send_sd_notify("STATUS=db watchdog send", logger=logger)  # test

    except Exception as e:
      # 如果连不上 DB 报错，故意不喂狗，让 Systemd 几秒后重启我们
      if logger:
        logger.exception(f"db watchdog health check failed: {e}")
      _send_sd_notify(f"STATUS=db watchdog health check failed, e={e}", logger=logger)

    await asyncio.sleep(watch_sleep_sec)


def _send_sd_notify(data: str, logger: logging.Logger | None = None):
  # 读取拦截后的 Socket 地址
  addr = os.getenv(_CUSTOM_NOTIFY_SOCKET_VAR_NAME)
  if not addr:
    return
  if addr.startswith("@"):
    addr = "\0" + addr[1:]
  try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
      sock.connect(addr)
      sock.sendall(data.encode())
  except Exception as e:
    if logger:
      logger.warning(f"Failed to send watchdog signal to systemd: {e}")
