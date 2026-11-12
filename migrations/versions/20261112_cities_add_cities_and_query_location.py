"""Add cities and query location."""

from alembic import op
import sqlalchemy as sa


revision = "20261112_cities"
down_revision = "9f40f757b48e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column(
            "id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    cities = sa.table(
        "cities",
        sa.column("id", sa.String(length=128)),
        sa.column("name", sa.Text()),
    )

    op.bulk_insert(
        cities,
        [
            {"id": "saratov", "name": "Саратов"},
            {"id": "engels", "name": "Энгельс"},
        ],
    )

    op.add_column(
        "search_queries",
        sa.Column(
            "city_id",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_search_queries_city_id",
        "search_queries",
        "cities",
        ["city_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_search_queries_city_id",
        "search_queries",
        ["city_id"],
        unique=False,
    )

    op.add_column(
        "query_results",
        sa.Column(
            "city_id_snapshot",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.add_column(
        "query_results",
        sa.Column(
            "category_id_snapshot",
            sa.String(length=128),
            nullable=True,
        ),
    )

    # Однократное распределение нашего исходного каталога.
    # Его однозначные городские записи имеют соответствующие суффиксы ID.
    op.execute(
        sa.text(
            """
            UPDATE search_queries
            SET city_id = 'saratov',
                updated_at = now()
            WHERE id ~ '(^|_)saratov$'
              AND city_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE search_queries
            SET city_id = 'engels',
                updated_at = now()
            WHERE id ~ '(^|_)engels$'
              AND city_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column(
        "query_results",
        "category_id_snapshot",
    )

    op.drop_column(
        "query_results",
        "city_id_snapshot",
    )

    op.drop_index(
        "ix_search_queries_city_id",
        table_name="search_queries",
    )

    op.drop_constraint(
        "fk_search_queries_city_id",
        "search_queries",
        type_="foreignkey",
    )

    op.drop_column(
        "search_queries",
        "city_id",
    )

    op.drop_table("cities")