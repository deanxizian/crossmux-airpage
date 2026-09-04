from __future__ import annotations

import json

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import Settings
from app.service import AirPageService


def main() -> int:
    settings = Settings.from_env()
    service = AirPageService(settings)
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(
        service.safe_scheduled_run,
        trigger="interval",
        minutes=settings.airpage_push_interval_minutes,
        id="render-and-push",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    print(
        json.dumps(
            {
                "event": "worker_started",
                "push_interval_minutes": settings.airpage_push_interval_minutes,
                "push_on_start": settings.airpage_push_on_start,
            },
            ensure_ascii=False,
        )
    )
    if settings.airpage_push_on_start:
        service.safe_scheduled_run()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
