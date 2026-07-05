from .scan import router as scan_router
from .feedback import router as feedback_router
from .report import router as report_router
from .reviews import router as reviews_router
from .device import router as device_router

__all__ = ["scan_router", "feedback_router", "report_router", "reviews_router", "device_router"]
