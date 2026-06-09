import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgressql+asyncpg://clinical_app:clinical-dev-password@postgres:5432/clinical"
)

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_session():
    async with async_session() as session:
        yield session