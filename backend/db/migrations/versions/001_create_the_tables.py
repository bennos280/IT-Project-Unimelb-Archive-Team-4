"""create the tables

Revision ID: 001
Revises: 
Create Date: 2026-10-08 22:37:10.203426

"""
import hashlib
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

TRANSCRIBE = Path(__file__).resolve().parents[3] / "pipeline" / "transcribe"


revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('bundles',
    sa.Column('bundle_id', sa.String(), nullable=False),
    sa.Column('source_pdf', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('bundle_id', name=op.f('pk_bundles'))
    )
    op.create_table('reviewers',
    sa.Column('reviewer_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('reviewer_id', name=op.f('pk_reviewers'))
    )
    op.create_table('instruction_versions',
    sa.Column('version_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('sha256', sa.String(), nullable=False),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.reviewer_id'], name=op.f('fk_instruction_versions_reviewer_id_reviewers')),
    sa.PrimaryKeyConstraint('version_id', name=op.f('pk_instruction_versions'))
    )
    op.create_table('page_types',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('built_in', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.reviewer_id'], name=op.f('fk_page_types_reviewer_id_reviewers')),
    sa.PrimaryKeyConstraint('name', name=op.f('pk_page_types'))
    )
    op.create_table('sorting_models',
    sa.Column('model_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('path', sa.String(), nullable=True),
    sa.Column('page_types', sa.Text(), nullable=False),
    sa.Column('pages', sa.Integer(), nullable=False),
    sa.Column('answered', sa.Integer(), nullable=False),
    sa.Column('wrong', sa.Integer(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.reviewer_id'], name=op.f('fk_sorting_models_reviewer_id_reviewers')),
    sa.PrimaryKeyConstraint('model_id', name=op.f('pk_sorting_models'))
    )
    op.create_table('surveys',
    sa.Column('survey_id', sa.String(), nullable=False),
    sa.Column('bundle_id', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.bundle_id'], name=op.f('fk_surveys_bundle_id_bundles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('survey_id', name=op.f('pk_surveys'))
    )
    op.create_table('pages',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('import_path', sa.String(), nullable=False),
    sa.Column('provider', sa.String(), nullable=True),
    sa.Column('model', sa.String(), nullable=True),
    sa.Column('effort', sa.String(), nullable=True),
    sa.Column('runtime', sa.Numeric(), nullable=True),
    sa.Column('revision_no', sa.Integer(), server_default='0', nullable=True),
    sa.Column('checked_revision', sa.Integer(), nullable=True),
    sa.Column('survey_id', sa.String(), nullable=True),
    sa.Column('bundle_id', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('prompt_version_id', sa.Integer(), nullable=True),
    sa.Column('template_version_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.bundle_id'], name=op.f('fk_pages_bundle_id_bundles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category'], ['page_types.name'], name=op.f('fk_pages_category_page_types')),
    sa.ForeignKeyConstraint(['prompt_version_id'], ['instruction_versions.version_id'], name=op.f('fk_pages_prompt_version_id_instruction_versions')),
    sa.ForeignKeyConstraint(['survey_id'], ['surveys.survey_id'], name=op.f('fk_pages_survey_id_surveys'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_version_id'], ['instruction_versions.version_id'], name=op.f('fk_pages_template_version_id_instruction_versions')),
    sa.PrimaryKeyConstraint('page_id', name=op.f('pk_pages'))
    )
    op.create_table('annotations',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('annotation_no', sa.Integer(), nullable=False),
    sa.Column('text_raw', sa.String(), nullable=True),
    sa.Column('location', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['page_id'], ['pages.page_id'], name=op.f('fk_annotations_page_id_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('page_id', 'annotation_no', name=op.f('pk_annotations'))
    )
    op.create_table('fields',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('field_title', sa.String(), nullable=False),
    sa.Column('text_raw', sa.Text(), nullable=True),
    sa.Column('decoded_value', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['page_id'], ['pages.page_id'], name=op.f('fk_fields_page_id_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('page_id', 'field_title', name=op.f('pk_fields'))
    )
    op.create_table('jobs',
    sa.Column('job_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('kind', sa.String(), server_default='bundle', nullable=False),
    sa.Column('pdf', sa.String(), nullable=True),
    sa.Column('page_id', sa.String(), nullable=True),
    sa.Column('page_type', sa.String(), nullable=True),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), server_default='waiting', nullable=False),
    sa.Column('step', sa.String(), nullable=True),
    sa.Column('done_pages', sa.Integer(), server_default='0', nullable=False),
    sa.Column('total_pages', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.CheckConstraint("kind IN ('bundle', 'page', 'train')", name=op.f('ck_jobs_kind')),
    sa.CheckConstraint("status IN ('waiting', 'running', 'done', 'failed')", name=op.f('ck_jobs_status')),
    sa.ForeignKeyConstraint(['page_id'], ['pages.page_id'], name=op.f('fk_jobs_page_id_pages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_type'], ['page_types.name'], name=op.f('fk_jobs_page_type_page_types')),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.reviewer_id'], name=op.f('fk_jobs_reviewer_id_reviewers')),
    sa.PrimaryKeyConstraint('job_id', name=op.f('pk_jobs'))
    )
    op.create_table('other_children',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('residence', sa.String(), nullable=False),
    sa.Column('child_no', sa.Integer(), nullable=False),
    sa.Column('text_raw', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['page_id'], ['pages.page_id'], name=op.f('fk_other_children_page_id_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('page_id', 'residence', 'child_no', name=op.f('pk_other_children'))
    )
    op.create_table('residents',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('resident_no', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['pages.page_id'], name=op.f('fk_residents_page_id_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('page_id', 'resident_no', name=op.f('pk_residents'))
    )
    op.create_table('flags',
    sa.Column('flag_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('field_title', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.CheckConstraint("kind IN ('inconsistency', 'gibberish', 'uncertain')", name=op.f('ck_flags_kind')),
    sa.ForeignKeyConstraint(['page_id', 'field_title'], ['fields.page_id', 'fields.field_title'], name=op.f('fk_flags_page_id_fields'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('flag_id', name=op.f('pk_flags'))
    )
    op.create_table('resident_fields',
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('resident_no', sa.Integer(), nullable=False),
    sa.Column('resident_field_title', sa.String(), nullable=False),
    sa.Column('text_raw', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['page_id', 'resident_no'], ['residents.page_id', 'residents.resident_no'], name=op.f('fk_resident_fields_page_id_residents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('page_id', 'resident_no', 'resident_field_title', name=op.f('pk_resident_fields'))
    )
    op.create_table('edits',
    sa.Column('edit_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('edit_text', sa.Text(), nullable=True),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('time', sa.DateTime(), nullable=True),
    sa.Column('page_id', sa.String(), nullable=False),
    sa.Column('field_title', sa.String(), nullable=True),
    sa.Column('resident_field_title', sa.String(), nullable=True),
    sa.Column('resident_no', sa.Integer(), nullable=True),
    sa.Column('child_residence', sa.String(), nullable=True),
    sa.Column('child_no', sa.Integer(), nullable=True),
    sa.Column('annotation_no', sa.Integer(), nullable=True),
    sa.CheckConstraint('(field_title IS NOT NULL) + (resident_field_title IS NOT NULL) + (child_no IS NOT NULL) + (annotation_no IS NOT NULL) = 1 AND (resident_field_title IS NULL) = (resident_no IS NULL) AND (child_residence IS NULL) = (child_no IS NULL)', name=op.f('ck_edits_exclusivity')),
    sa.ForeignKeyConstraint(['page_id', 'annotation_no'], ['annotations.page_id', 'annotations.annotation_no'], name=op.f('fk_edits_page_id_annotations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_id', 'child_residence', 'child_no'], ['other_children.page_id', 'other_children.residence', 'other_children.child_no'], name=op.f('fk_edits_page_id_other_children'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_id', 'field_title'], ['fields.page_id', 'fields.field_title'], name=op.f('fk_edits_page_id_fields'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['page_id', 'resident_field_title', 'resident_no'], ['resident_fields.page_id', 'resident_fields.resident_field_title', 'resident_fields.resident_no'], name=op.f('fk_edits_page_id_resident_fields'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.reviewer_id'], name=op.f('fk_edits_reviewer_id_reviewers')),
    sa.PrimaryKeyConstraint('edit_id', name=op.f('pk_edits'))
    )
    #the four page types the code is built around
    op.bulk_insert(sa.table('page_types', sa.column('name', sa.String), sa.column('built_in', sa.Boolean)),
                   [{'name': name, 'built_in': True} for name in ('main', 'notes', 'coded', 'other')])
    #version 1 of the prompt and of each template is the file byte for byte, so transcripts made from the files match it
    versions = sa.table('instruction_versions', sa.column('kind', sa.String), sa.column('body', sa.Text), sa.column('sha256', sa.String))
    files = {'prompt': TRANSCRIBE / 'prompt.txt', **{path.stem: path for path in sorted((TRANSCRIBE / 'templates').glob('*.json'))}}
    op.bulk_insert(versions, [{'kind': kind, 'body': path.read_bytes().decode('utf-8'),
                               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for kind, path in files.items()])


def downgrade() -> None:
    raise NotImplementedError("the first migration can't be undone: delete backend/db/wilfprestsurvey.db for a fresh db")
