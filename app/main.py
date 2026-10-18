from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.mock import MockTransport
from app.api.routes import router
from app.config import Settings
from app.workflow.jobs import Jobs


def create_app(*, settings=None, workflow=None, transport=None, format_sms=None):
    settings = settings or Settings()
    if settings.enable_mock_sms and (workflow is None or format_sms is None):
        raise ValueError("Mock simulation requires an injected workflow and D SMS formatter")
    @asynccontextmanager
    async def lifespan(app):
        yield
        await app.state.jobs.close()

    app = FastAPI(title="VIZS shopping assistant", lifespan=lifespan)
    app.state.settings = settings
    app.state.workflow = workflow
    app.state.jobs = Jobs(settings)
    app.state.transport = transport or MockTransport()
    app.state.format_sms = format_sms
    app.include_router(router)
    return app


app = create_app()
