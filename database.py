from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, BigInteger, Boolean, select, and_
import config

engine = create_async_engine(config.DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase): 
    pass

# ==========================================
# 🗄 BAZA JADVALLARI (MODELS)
# ==========================================
class Operator(Base):
    __tablename__ = 'operators'
    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PhoneNumber(Base):
    __tablename__ = 'phone_numbers'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    client_name: Mapped[str] = mapped_column(String(100), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")
    operator_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Booking(Base):
    __tablename__ = 'bookings'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operator_id: Mapped[int] = mapped_column(BigInteger)
    client_name: Mapped[str] = mapped_column(String(100))
    problem: Mapped[str] = mapped_column(String(255))
    booking_time: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# 🆕 TIZIM SOZLAMALARI UCHUN YANGI JADVAL
class BotSetting(Base):
    __tablename__ = 'bot_settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    distribution_active: Mapped[bool] = mapped_column(Boolean, default=False) # Boshida tarqatish o'chiq bo'ladi

# ==========================================
# ⚙️ BAZA FUNKSIYALARI VA TRANZAKSIYALAR
# ==========================================
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# 🆕 SOZLAMALAR FUNKSIYASI (TARQATISH HOLATINI OLISH)
async def get_distribution_status() -> bool:
    async with AsyncSessionLocal() as session:
        setting = await session.get(BotSetting, 1)
        if not setting:
            setting = BotSetting(id=1, distribution_active=False)
            session.add(setting)
            await session.commit()
        return setting.distribution_active

# 🆕 SOZLAMALAR FUNKSIYASI (TARQATISHNI YOQISH/O'CHIRISH)
async def toggle_distribution_status() -> bool:
    async with AsyncSessionLocal() as session:
        setting = await session.get(BotSetting, 1)
        if not setting:
            setting = BotSetting(id=1, distribution_active=True)
            session.add(setting)
        else:
            setting.distribution_active = not setting.distribution_active
        await session.commit()
        return setting.distribution_active

async def add_phone_number(number: str, client_name: str = None, location: str = None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PhoneNumber).where(PhoneNumber.number == number))
        if not result.scalar_one_or_none():
            new_phone = PhoneNumber(number=number, client_name=client_name, location=location)
            session.add(new_phone)
            await session.commit()

async def get_number_for_operator(operator_id: int):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(PhoneNumber).where(PhoneNumber.status == "new")\
                .order_by(PhoneNumber.created_at).limit(1).with_for_update(skip_locked=True)
            result = await session.execute(stmt)
            phone = result.scalar_one_or_none()
            if phone:
                phone.status = "assigned"
                phone.operator_id = operator_id
                phone.updated_at = datetime.utcnow()
                await session.flush()
                return phone
            return None

async def check_booking_conflict(target_time: datetime) -> bool:
    async with AsyncSessionLocal() as session:
        start_time = target_time - timedelta(minutes=29)
        end_time = target_time + timedelta(minutes=29)
        stmt = select(Booking).where(and_(Booking.booking_time >= start_time, Booking.booking_time <= end_time))
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None