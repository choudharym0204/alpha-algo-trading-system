from __future__ import annotations


from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db import Base, TimestampMixin


class SampleModel(TimestampMixin, Base):
    __tablename__ = "sample_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


def test_base_uses_expected_naming_convention() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert Base.metadata.naming_convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"


def test_sample_model_maps_columns() -> None:
    table = SampleModel.__table__

    assert table.name == "sample_models"
    assert set(table.c.keys()) == {"id", "name", "created_at", "updated_at"}
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
