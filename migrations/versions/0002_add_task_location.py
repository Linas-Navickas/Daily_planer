"""Add a location field to planner tasks."""

import sqlalchemy as sa
from alembic import op


revision = "0002_add_task_location"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("location", sa.Text(), nullable=False, server_default=""))


def downgrade():
    op.drop_column("tasks", "location")
