import time
import uuid

from fastapi import Request


async def request_handler_middleware(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time-MS"] = str(elapsed_ms)
    return response
