import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "silatsense-disposable-tests-only-signing-key"
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import Base, get_db
from app.models.entities import User, Movement
from app.core.security import passwords
from app.repositories.training import seed_movements


@pytest.fixture
def client():
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        from sqlalchemy.engine import make_url

        assert make_url(test_url).database.endswith("_test"), (
            "Only disposable *_test databases are permitted"
        )
        engine = create_engine(test_url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with factory() as db:
        db.add(
            User(
                name="Coach",
                email="coach@example.com",
                role="COACH",
                password_hash=passwords.hash("password123"),
            )
        )
        seed_movements(db)
        db.commit()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def member(client):
    r = client.post(
        "/api/v1/auth/sign-up",
        json={
            "fullName": "Member One",
            "identifier": "one@example.com",
            "password": "password123",
        },
    )
    assert r.status_code == 201
    return {"Authorization": "Bearer " + r.json()["accessToken"]}
