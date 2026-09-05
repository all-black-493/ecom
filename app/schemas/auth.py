from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    signup_channel: str = "organic"
    signup_country: str = Field("US", min_length=2, max_length=2)
    marketing_opt_in: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    first_name: str
    last_name: str
    signup_channel: str
    signup_country: str
    marketing_opt_in: bool


class TokenOut(BaseModel):
    """Returned by API clients that want the JWT explicitly (not just the cookie)."""

    access_token: str
    token_type: str = "bearer"
    expires_in_days: int = 7
    customer: CustomerOut
