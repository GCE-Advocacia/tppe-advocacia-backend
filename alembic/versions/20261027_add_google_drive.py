"""Google Drive connection, per-process folders and document storage.

Revision ID: 8e9f0a1b2c3d
Revises: 7d8e9f0a1b2c
"""

import sqlalchemy as sa

from alembic import op

revision = "8e9f0a1b2c3d"
down_revision = "7d8e9f0a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_drive_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("root_folder_id", sa.String(128), nullable=True),
        sa.Column("connected_by", sa.Integer(), nullable=True),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connected_by"],
            ["users.id"],
            name="fk_google_drive_connection_connected_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_google_drive_connection_id"), "google_drive_connection", ["id"]
    )
    op.create_table(
        "process_drive_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("folder_id", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["processes.id"],
            name="fk_process_drive_folders_process_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("process_id"),
    )
    op.create_index(
        op.f("ix_process_drive_folders_id"), "process_drive_folders", ["id"]
    )
    op.add_column(
        "process_documents",
        sa.Column("storage", sa.String(10), nullable=False, server_default="local"),
    )


def downgrade() -> None:
    op.drop_column("process_documents", "storage")
    op.drop_index(op.f("ix_process_drive_folders_id"), "process_drive_folders")
    op.drop_table("process_drive_folders")
    op.drop_index(op.f("ix_google_drive_connection_id"), "google_drive_connection")
    op.drop_table("google_drive_connection")
