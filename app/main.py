from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.mock import MockTransport
from app.api.routes import router
from app.config import Settings
from app.decision import format_sms as default_format_sms
from app.workflow.jobs import Jobs
from app.workflow.runtime import runtime_workflow


def create_app(*, settings=None, workflow=None, transport=None, format_sms=None,
               xai_transport=None, tavily_transport=None, destination_validator=None):
    settings = settings if settings is not None else Settings.from_env()
    if settings.enable_mock_sms and workflow is not None and format_sms is None:
        raise ValueError("Injected mock workflow requires an explicit SMS formatter")

    @asynccontextmanager
    async def lifespan(app):
        if workflow is not None:
            try:
                yield
            finally:
                await app.state.jobs.close()
        else:
            options = dict(xai_transport=xai_transport, tavily_transport=tavily_transport)
            if destination_validator is not None:
                options["destination_validator"] = destination_validator
            async with runtime_workflow(settings, **options) as assembled:
                app.state.workflow = assembled
                try:
                    yield
                finally:
                    # Cancel jobs before the provider HTTP client closes.
                    await app.state.jobs.close()
                    app.state.workflow = None

    app = FastAPI(title="VIZS shopping assistant", lifespan=lifespan)
    app.state.settings = settings
    app.state.workflow = workflow
    app.state.jobs = Jobs(settings)
    app.state.transport = transport or MockTransport()
    app.state.format_sms = format_sms or default_format_sms
    app.include_router(router)
    return app


app = create_app()
