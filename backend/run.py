"""启动入口：强制 ProactorEventLoop 以支持 Playwright 浏览器子进程

uvicorn 在 reload/worker 模式下会强制 SelectorEventLoop，
已通过 patch uvicorn/loops/asyncio.py 修复。
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print(f"[启动] 事件循环策略: {type(asyncio.get_event_loop_policy()).__name__}")


if __name__ == "__main__":
    import uvicorn
    sys.path.insert(0, ".")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
