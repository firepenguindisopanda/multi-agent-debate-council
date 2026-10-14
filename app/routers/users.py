from app.dependencies import AdminDep, SessionDep
from app.repositories.user import UserRepository
from app.schemas import UserResponse
from app.services.user_service import UserService

from . import api_router


@api_router.get("/users", response_model=list[UserResponse])
async def list_users(admin: AdminDep, db: SessionDep):
    return UserService(UserRepository(db)).get_all_users()
