from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.web.templating import env

templates = Jinja2Templates(env=env)
static_files = StaticFiles(directory="app/static")

router = APIRouter(tags=["Pages"], include_in_schema=get_settings().is_dev)
api_router = APIRouter(tags=["API"], prefix="/api")

from . import (  # noqa: E402,F401
    admin_home,
    api_debates,
    debates,
    index,
    login,
    logout,
    register,
    users,
)
