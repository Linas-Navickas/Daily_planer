"""Add a location field to planner tasks."""

import sqlalchemy as sa
from alembic import op


revision = "0002_add_task_location"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("location", sa.Text(), nullable=False, server_default="")
        )


def downgrade():
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("location")
