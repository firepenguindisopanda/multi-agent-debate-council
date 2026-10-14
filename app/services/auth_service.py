from typing import Optional

from sqlmodel import select

from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import SignupRequest
from app.schemas.user import RegularUserCreate
from app.services.errors import ConflictError
from app.utilities.security import create_access_token, encrypt_password, verify_password


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        user = self.user_repo.get_by_username(username.strip())
        if not user or not verify_password(
            plaintext_password=password, encrypted_password=user.password
        ):
            return None
        return create_access_token(data={"sub": f"{user.id}", "role": user.role})

    def register_user(self, signup: SignupRequest) -> User:
        db = self.user_repo.db
        if db.exec(select(User).where(User.username == signup.username)).first():
            raise ConflictError("That username is taken.")
        if db.exec(select(User).where(User.email == signup.email)).first():
            raise ConflictError("An account with that email already exists.")
        return self.user_repo.create(
            RegularUserCreate(
                username=signup.username,
                email=signup.email,
                password=encrypt_password(signup.password),
            )
        )
