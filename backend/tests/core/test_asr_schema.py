"""只验证 ASR nullable language 增量迁移与配套配置，全部使用临时库。"""
import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from src.config.settings import Settings
from src.db.models import ASRSession, Customer, Fact, SalesInput, Session
from src.db.session import create_database, init_db


@pytest.mark.asyncio
async def test_old_asr_schema_adds_language_without_rebuilding_or_losing_rows(tmp_path):
    engine, factory = create_database(Settings(database_path=str(tmp_path / "old.db")))
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("""CREATE TABLE asr_sessions (
                id VARCHAR PRIMARY KEY, created_at VARCHAR NOT NULL,
                session_id VARCHAR NOT NULL, state VARCHAR NOT NULL,
                finished_at VARCHAR, error_code VARCHAR, duration_seconds FLOAT)""")
            await conn.exec_driver_sql("""INSERT INTO asr_sessions
                (id,created_at,session_id,state,error_code,duration_seconds)
                VALUES ('old-asr','2026-09-20T00:00:00Z','old-session','failed','ASR_DISCONNECTED',3.5)""")
            original_rootpage = (await conn.exec_driver_sql(
                "SELECT rootpage FROM sqlite_master WHERE name='asr_sessions'")).scalar_one()
        await init_db(engine)
        # 多次启动不重复 ADD COLUMN，也不改旧记录为假定语言。
        await init_db(engine)
        async with factory() as db:
            row = await db.get(ASRSession, "old-asr")
            assert row is not None
            assert row.language is None
            assert (row.session_id, row.state, row.error_code, row.duration_seconds) == (
                "old-session", "failed", "ASR_DISCONNECTED", 3.5)
        async with engine.connect() as conn:
            columns = await conn.run_sync(lambda connection: inspect(connection).get_columns("asr_sessions"))
            assert [col["name"] for col in columns].count("language") == 1
            assert next(col for col in columns if col["name"] == "language")["nullable"]
            current_rootpage = (await conn.exec_driver_sql(
                "SELECT rootpage FROM sqlite_master WHERE name='asr_sessions'")).scalar_one()
            assert current_rootpage == original_rootpage
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_new_schema_keeps_selected_language_after_repeated_initialization(tmp_path):
    engine, factory = create_database(Settings(database_path=str(tmp_path / "new.db")))
    try:
        await init_db(engine)
        async with factory() as db:
            customer = Customer(nickname="隔离客户", normalized_email="test@example.com")
            db.add(customer)
            await db.flush()
            session = Session(customer_id=customer.id, title="语言测试")
            db.add(session)
            await db.flush()
            asr = ASRSession(session_id=session.id, language="zh")
            db.add(asr)
            await db.commit()
            asr_id = asr.id
        await init_db(engine)
        async with factory() as db:
            restored = await db.get(ASRSession, asr_id)
            assert restored is not None and restored.language == "zh"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("field,value", [
    ("map_image_width", 0), ("map_image_width", 1025),
    ("map_image_height", 0), ("map_image_height", 1025),
    ("energy_max_years", 0), ("energy_max_years", -1),
])
def test_map_and_energy_configuration_rejects_invalid_bounds(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_map_and_energy_configuration_defaults_and_boundaries():
    settings = Settings()
    assert settings.energy_max_years == 100
    assert (settings.map_image_width, settings.map_image_height) == (750, 300)
    assert Settings(map_image_width=1, map_image_height=1024, energy_max_years=1).energy_max_years == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_state", [
    "created", "connecting", "streaming", "finishing", "finished", "failed", "discarded",
])
async def test_restart_interrupts_only_unfinished_audio_without_modifying_inputs(tmp_path, initial_state):
    engine, factory = create_database(Settings(database_path=str(tmp_path / "restart.db")))
    final_states = {"finished", "failed", "discarded"}
    old_finished_at = "2026-09-20T00:00:00Z" if initial_state in final_states else None
    old_error = "ORIGINAL_ERROR" if initial_state == "failed" else None
    try:
        await init_db(engine)
        async with factory() as db:
            customer = Customer(nickname="重启测试", normalized_email="restart@example.com")
            db.add(customer)
            await db.flush()
            session = Session(customer_id=customer.id, title="已发送复盘保留")
            db.add(session)
            await db.flush()
            asr = ASRSession(session_id=session.id, state=initial_state, language="zh",
                             finished_at=old_finished_at, error_code=old_error)
            db.add(asr)
            await db.flush()
            sales_input = SalesInput(session_id=session.id, asr_session_id=asr.id,
                                      corrected_text="已确认的复盘信息", source="asr_corrected")
            fact = Fact(session_id=session.id, key="monthly_budget", value=400000,
                        state="confirmed", source_kind="sales_input", source_id=asr.id)
            db.add_all([sales_input, fact])
            await db.commit()
            asr_id, input_id, fact_id = asr.id, sales_input.id, fact.id
        await init_db(engine)
        async with factory() as db:
            restored = await db.get(ASRSession, asr_id)
            assert restored is not None and restored.language == "zh"
            if initial_state in final_states:
                assert (restored.state, restored.error_code, restored.finished_at) == (
                    initial_state, old_error, old_finished_at)
            else:
                assert restored.state == "failed" and restored.error_code == "ASR_INTERRUPTED"
                assert restored.finished_at is not None
            first_finished_at = restored.finished_at
            kept_input = await db.get(SalesInput, input_id)
            kept_fact = await db.get(Fact, fact_id)
            assert kept_input is not None and kept_input.corrected_text == "已确认的复盘信息"
            assert kept_fact is not None and kept_fact.value == 400000 and kept_fact.state == "confirmed"
        # 再次启动不刷新已终结记录的结束时间，恢复动作本身可重复。
        await init_db(engine)
        async with factory() as db:
            final = await db.get(ASRSession, asr_id)
            assert final is not None and final.finished_at == first_finished_at
    finally:
        await engine.dispose()
