from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(Text, primary_key=True)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    sid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    traffic_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    hwid: Mapped[str] = mapped_column(Text, nullable=False)
    device_os: Mapped[str] = mapped_column(Text, nullable=False)
    ver_os: Mapped[str] = mapped_column(Text, nullable=False)
    device_model: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str] = mapped_column(Text, nullable=False)


class Traffic(Base):
    __tablename__ = "traffic"
    __table_args__ = (
        Index("traffic_ts", "ts"),
        Index("traffic_user", "username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(Text, nullable=False)
    server: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    tx: Mapped[int] = mapped_column(Integer, nullable=False)
    rx: Mapped[int] = mapped_column(Integer, nullable=False)


class Host(Base):
    __tablename__ = "hosts"

    address: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    api_address: Mapped[str] = mapped_column(Text, nullable=False)
    api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class HostTag(Base):
    __tablename__ = "host_tags"

    host_address: Mapped[str] = mapped_column(Text, primary_key=True)
    tag: Mapped[str] = mapped_column(Text, primary_key=True)


class UserTag(Base):
    __tablename__ = "user_tags"

    username: Mapped[str] = mapped_column(Text, primary_key=True)
    tag: Mapped[str] = mapped_column(Text, primary_key=True)


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
