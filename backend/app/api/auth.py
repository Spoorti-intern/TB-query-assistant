
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    OTPSendRequest, OTPSendResponse, OTPVerifyRequest,
    LoginOTPSendRequest, LoginOTPVerifyRequest,
)
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user
from app.core.otp import generate_otp, store_otp, verify_otp, send_otp_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/send-otp", response_model=OTPSendResponse)
async def send_otp(data: OTPSendRequest, db: Session = Depends(get_db)):
    """Send OTP to email for registration verification."""
    # Allow re-registration with same email — will update existing account
    existing_username = db.query(User).filter(
        User.username == data.username,
        func.lower(User.email) != data.email.lower()
    ).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    code = generate_otp()
    store_otp(db, data.email, code)
    email_sent, error_reason = send_otp_email(data.email, code)

    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP email. {error_reason}"
        )

    return OTPSendResponse(
        message="OTP sent to your email address",
        email=data.email,
    )


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_and_register(data: OTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify OTP and complete registration. Allows re-registration with same email."""
    if not verify_otp(db, data.email, data.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please request a new one."
        )

    # Check if email already exists — update instead of blocking
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if user:
        # Update existing account with new credentials
        user.username = data.username
        user.hashed_password = hash_password(data.password)
        db.commit()
        db.refresh(user)
    else:
        # Check username not taken by another user
        existing_username = db.query(User).filter(User.username == data.username).first()
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse)
async def register(data: UserRegister, db: Session = Depends(get_db)):
    # Check if email already exists — update existing account
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if user:
        user.username = data.username
        user.hashed_password = hash_password(data.password)
        db.commit()
        db.refresh(user)
    else:
        # Check if username already exists for new accounts
        existing = db.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/send-login-otp", response_model=OTPSendResponse)
async def send_login_otp(data: LoginOTPSendRequest, db: Session = Depends(get_db)):
    """Validate credentials and send OTP for login verification."""
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    code = generate_otp()
    store_otp(db, data.email, code)
    email_sent, error_reason = send_otp_email(data.email, code)

    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP email. {error_reason}"
        )

    return OTPSendResponse(
        message="OTP sent to your email address",
        email=data.email,
    )


@router.post("/verify-login-otp", response_model=TokenResponse)
async def verify_login_otp(data: LoginOTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify login OTP and return access token."""
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not verify_otp(db, data.email, data.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please request a new one."
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.get("/smtp-check")
async def smtp_check():
    """Debug endpoint to check if SMTP env vars are loaded."""
    import os
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")
    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user_set": bool(smtp_user),
        "smtp_pass_set": bool(smtp_pass),
        "smtp_user_preview": smtp_user[:3] + "***" if smtp_user else "(empty)",
    }
