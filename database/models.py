from decimal import Decimal
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime,
    ForeignKey, Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id           = Column(BigInteger, primary_key=True)          # Telegram ID
    username     = Column(String(64),  nullable=True)
    first_name   = Column(String(64),  nullable=False)
    balance      = Column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    total_earned = Column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    referrer_id  = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ⭐ VIP
    is_vip         = Column(Boolean,  default=False, nullable=False)
    vip_expires_at = Column(DateTime(timezone=True), nullable=True)

    is_banned    = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relations
    vip_subscriptions = relationship("VIPSubscription", back_populates="user", lazy="selectin")
    task_submissions  = relationship("TaskSubmission",  back_populates="user")
    withdrawals       = relationship("Withdrawal",      back_populates="user")
    referrals_given   = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referrals_received = relationship("Referral", foreign_keys="Referral.referred_id", back_populates="referred")


# ─────────────────────────────────────────────
# VIP SUBSCRIPTIONS  (аудит кожної оплати)
# ─────────────────────────────────────────────
class VIPSubscription(Base):
    __tablename__ = "vip_subscriptions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    duration_days  = Column(Integer, nullable=False)               # 1 / 7 / 30
    payment_method = Column(String(20), nullable=False)            # 'stars' | 'balance' | 'admin'
    amount_paid    = Column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    stars_paid     = Column(Integer, nullable=True)
    activated_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at     = Column(DateTime(timezone=True), nullable=False)
    granted_by_admin = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="vip_subscriptions")


# ─────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────
class Task(Base):
    __tablename__ = "tasks"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    title               = Column(String(256), nullable=False)
    description         = Column(Text,        nullable=False)
    referral_link       = Column(String(512), nullable=False)
    reward              = Column(Numeric(12, 2), nullable=False)
    execution_limit     = Column(Integer, nullable=True)
    time_limit_minutes  = Column(Integer, nullable=True)
    is_active           = Column(Boolean, default=True,  nullable=False)
    is_vip_only         = Column(Boolean, default=False, nullable=False)  # ⭐ VIP
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    submissions = relationship("TaskSubmission", back_populates="task")


# ─────────────────────────────────────────────
# TASK SUBMISSIONS
# ─────────────────────────────────────────────
class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    task_id       = Column(Integer,    ForeignKey("tasks.id"), nullable=False)
    proof_text      = Column(Text,           nullable=True)
    proof_file_id   = Column(String(256),    nullable=True)
    status          = Column(String(20),     default="pending", nullable=False)  # pending|approved|rejected
    reward_snapshot = Column(Numeric(12, 2), nullable=False)   # фіксуємо суму в момент подачі
    submitted_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at     = Column(DateTime(timezone=True), nullable=True)
    reject_reason   = Column(Text, nullable=True)

    user = relationship("User", back_populates="task_submissions")
    task = relationship("Task", back_populates="submissions")


# ─────────────────────────────────────────────
# WITHDRAWALS
# ─────────────────────────────────────────────
class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount       = Column(Numeric(12, 2), nullable=False)
    currency     = Column(String(10), nullable=False)   # uah|rub|usdt|ton|stars
    requisites   = Column(Text, nullable=False)
    status       = Column(String(20), default="pending", nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="withdrawals")


# ─────────────────────────────────────────────
# REFERRALS
# ─────────────────────────────────────────────
class Referral(Base):
    __tablename__ = "referrals"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id    = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    referred_id    = Column(BigInteger, ForeignKey("users.id"), nullable=False, unique=True)
    bonus_credited = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_given")
    referred = relationship("User", foreign_keys=[referred_id], back_populates="referrals_received")
