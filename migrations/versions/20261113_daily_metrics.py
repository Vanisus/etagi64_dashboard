import sqlalchemy as sa
from alembic import op

revision = "20261113_daily"
down_revision = "18378751c907"
branch_labels = None

depends_on = None


def upgrade() -> None:
    op.create_index("ix_search_queries_city_enabled_category", "search_queries", ["city_id", "enabled", "category_id"])
    op.create_index("ix_collection_runs_status_started", "collection_runs", ["status", "started_at"])
    op.create_index("ix_collection_runs_active_key", "collection_runs", [sa.text("(parameters ->> 'request_key')")], postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.add_column("cities", sa.Column("yandex_region_id", sa.String(32), nullable=True))
    op.execute("UPDATE cities SET yandex_region_id = '194' WHERE id = 'saratov'")
    op.execute("UPDATE cities SET yandex_region_id = '11147' WHERE id = 'engels'")
    op.create_table(
        "daily_query_metrics",
        sa.Column("query_id", sa.String(128), sa.ForeignKey("search_queries.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("region_id", sa.String(32), primary_key=True),
        sa.Column("metric_date", sa.Date(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("collection_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("phrase_snapshot", sa.Text(), nullable=False),
        sa.Column("city_id_snapshot", sa.String(128), nullable=False),
        sa.Column("category_id_snapshot", sa.String(128), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("count >= 0", name="ck_daily_query_metrics_count"),
    )
    op.create_index("ix_daily_query_metrics_region_date", "daily_query_metrics", ["region_id", "metric_date"])


def downgrade() -> None:
    op.drop_index("ix_collection_runs_active_key", table_name="collection_runs")
    op.drop_index("ix_collection_runs_status_started", table_name="collection_runs")
    op.drop_index("ix_search_queries_city_enabled_category", table_name="search_queries")
    op.drop_index("ix_daily_query_metrics_region_date", table_name="daily_query_metrics")
    op.drop_table("daily_query_metrics")
    op.drop_column("cities", "yandex_region_id")
