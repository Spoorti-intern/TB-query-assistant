
import uuid

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)

    # Credits & payment
    credits = Column(Integer, default=2, nullable=False)
    has_paid = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    payments = relationship("Payment", back_populates="user", order_by="Payment.created_at.desc()")


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(Float, nullable=False)  # Unix timestamp
    used = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    card_last4 = Column(String(4), nullable=False)
    card_brand = Column(String(20), default="Visa")
    credits_added = Column(Integer, default=50, nullable=False)
    status = Column(String(20), default="completed", nullable=False)  # completed, failed, refunded

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    user = relationship("User", back_populates="payments")
