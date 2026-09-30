import pytest

from app import seed as seed_module
from app.infrastructure.db.models import Base
from app.infrastructure.db.session import build_engine, build_session_factory
from app.infrastructure.security import JwtTokenService, ScryptPasswordHasher

pytestmark = pytest.mark.integration


def test_seed_creates_demo_data_once():
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    hasher = ScryptPasswordHasher(n=2**10, p=1)
    tokens = JwtTokenService("seed-test-secret-long-enough-for-hs256")

    with build_session_factory(engine)() as session:
        result = seed_module.seed(session, hasher, tokens, "demo-password")
        again = seed_module.seed(session, hasher, tokens, "demo-password")
    engine.dispose()

    assert again is None
    assert result.task_lists == 3
    assert result.tasks == 12
    assert result.users["bob"].email_verified
    assert not result.users["carla"].email_verified
    assert tokens.decode(result.carla_verification_token, "email_verification") == str(
        result.users["carla"].id
    )


@pytest.mark.parametrize(
    ("env", "message"),
    [({"APP_ENV": "production"}, "production"), ({"SEED_PASSWORD": ""}, "SEED_PASSWORD")],
)
def test_seed_refuses_unsafe_runs(monkeypatch, env, message):
    monkeypatch.setenv("JWT_SECRET", "seed-test-secret-long-enough-for-hs256")
    monkeypatch.setenv("SEED_PASSWORD", "demo-password")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    seed_module.get_settings.cache_clear()

    with pytest.raises(SystemExit, match=message):
        seed_module.main()
    seed_module.get_settings.cache_clear()
