
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class OTPSendRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class OTPSendResponse(BaseModel):
    message: str
    email: str


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    otp: str


class LoginOTPSendRequest(BaseModel):
    email: str
    password: str


class LoginOTPVerifyRequest(BaseModel):
    email: str
    password: str
    otp: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    credits: int = 2
    has_paid: bool = False
    is_admin: bool = False

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Payment schemas
class PaymentRequest(BaseModel):
    card_number: str
    card_expiry: str = ""
    card_cvc: str = ""
    card_name: str
    amount: float = 9.99


class PaymentResponse(BaseModel):
    id: str
    amount: float
    card_last4: str
    card_brand: str
    credits_added: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Admin schemas
class AdminUserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    credits: int
    has_paid: bool
    is_admin: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminCreditAllocation(BaseModel):
    user_id: str
    credits: int


class AdminTransactionResponse(BaseModel):
    id: str
    user_id: str
    username: str
    email: str
    amount: float
    card_last4: str
    card_brand: str
    credits_added: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
