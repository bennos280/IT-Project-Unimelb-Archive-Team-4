from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric,
                        String, Text, UniqueConstraint, false, func, text)
from backend.db.database import Base

#a set of documents digitised together, with its own bundles and page types; the Wilfred Prest Survey is collection 1
class Collection(Base):
    __tablename__ = "collections"
    collection_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    record_key = Column(String, nullable=True) #the field holding a survey's number, which ties its pages together; None: page order only
    archive_series = Column(Integer, nullable=True) #its series on archives.library.unimelb.edu.au: /nodes/view/<archive_series>
    archive_identifier = Column(String, nullable=True) #the series' catalogue identifier (UMA-SR-...), title and number of
    archive_title = Column(String, nullable=True) #items, as the archive showed them when the series was linked
    archive_items = Column(Integer, nullable=True)

#an item of a collection's archive series, as the archive lists it
#ponytail: only the Wilfred Prest Survey's items are listed (migration 013); list a series' items from the archive when another can import
class ArchiveItem(Base):
    __tablename__ = "archive_items"
    node = Column(Integer, primary_key=True) #its page on the archive, /nodes/view/<node>, and its bundle number
    collection_id = Column(Integer, ForeignKey("collections.collection_id"), nullable=False)
    identifier = Column(String, nullable=False) #its catalogue identifier, UMA-ITE-...
    title = Column(String, nullable=False)

#ponytail: a new bundle or page type joins collection 1 until there is a way to choose one
class Bundle(Base):
    __tablename__ = "bundles"
    bundle_id = Column(String, primary_key=True)
    source_pdf = Column(String, nullable=False)
    collection_id = Column(Integer, ForeignKey("collections.collection_id"), nullable=False, server_default="1")

class Survey(Base):
    __tablename__ = "surveys"
    survey_id = Column(String, primary_key=True)
    bundle_id = Column(String, ForeignKey("bundles.bundle_id", ondelete="CASCADE"), nullable=False)

#the kinds of page; the four built in (main, notes, coded, other) can't be removed, others are added from the review screen.
#name: the id that pages, jobs and templates use, unique across collections; label: what people see, unique within a collection
class PageType(Base):
    __tablename__ = "page_types"
    __table_args__ = (UniqueConstraint("collection_id", "label"),
                      Index("uq_page_types_unknown", "collection_id", unique=True, sqlite_where=text("unknown"))) #one per collection
    name = Column(String, primary_key=True)
    collection_id = Column(Integer, ForeignKey("collections.collection_id"), nullable=False, server_default="1")
    label = Column(String, nullable=False, default=lambda ctx: ctx.get_current_parameters()["name"]) #the name if not given
    #its collection's Unknown type: a page sorting couldn't place waits here, unread and flagged, for a reviewer to pick its type
    unknown = Column(Boolean, nullable=False, default=False, server_default=false())
    starts_record = Column(Boolean, nullable=False, default=False, server_default=false()) #a page of this type starts a survey
    #a page of this type joins the survey whose number it shows, not just the one it follows
    matched_by_key = Column(Boolean, nullable=False, default=False, server_default=false())
    built_in = Column(Boolean, nullable=False, default=False, server_default=false())
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=True) #None: built in
    created_at = Column(DateTime, nullable=True, server_default=func.now()) #UTC

class Page(Base):
    __tablename__ = "pages"
    page_id = Column(String, primary_key=True)
    import_path = Column(String, nullable=False)
    provider = Column(String, nullable=True) #claude or codex
    model = Column(String, nullable=True)
    effort = Column(String, nullable=True)
    runtime = Column(Numeric, nullable=True)
    revision_no = Column(Integer, default=0, server_default="0")
    needs_transcription = Column(Boolean, nullable=False, default=False, server_default=false())
    checked_revision = Column(Integer, nullable=True) #the revision a reviewer last saved: checked while it is still revision_no
    survey_id = Column(String, ForeignKey("surveys.survey_id", ondelete="CASCADE"), nullable=True)
    bundle_id = Column(String, ForeignKey("bundles.bundle_id", ondelete="CASCADE"), nullable=False)
    category = Column(String, ForeignKey("page_types.name"), nullable=False)
    #the prompt and template that read the page; None: read before versions, or from files matching no version
    prompt_version_id = Column(Integer, ForeignKey("instruction_versions.version_id"), nullable=True)
    template_version_id = Column(Integer, ForeignKey("instruction_versions.version_id"), nullable=True)

class Field(Base):
    __tablename__ = "fields"
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), primary_key=True)
    field_title = Column(String, primary_key=True)
    text_raw = Column(Text, nullable=True)
    decoded_value = Column(Text, nullable=True)

#something for the reviewer to check on a field
class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        ForeignKeyConstraint(["page_id", "field_title"], ["fields.page_id", "fields.field_title"], ondelete="CASCADE"),
        CheckConstraint("kind IN ('inconsistency', 'gibberish', 'uncertain')", name="kind"),
    )
    flag_id = Column(Integer, primary_key=True, autoincrement=True)
    page_id = Column(String, nullable=False)
    field_title = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    reason = Column(Text, nullable=False)

#residents, children and annotations are numbered from 0 in page order
class Resident(Base):
    __tablename__ = "residents"
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), primary_key=True)
    resident_no = Column(Integer, primary_key=True)

class ResidentField(Base):
    __tablename__ = "resident_fields"
    __table_args__ = (ForeignKeyConstraint(["page_id", "resident_no"], ["residents.page_id", "residents.resident_no"],
                                           ondelete="CASCADE"),)
    page_id = Column(String, primary_key=True)
    resident_no = Column(Integer, primary_key=True)
    resident_field_title = Column(String, primary_key=True)
    text_raw = Column(String, nullable=True)

class Reviewer(Base):
    __tablename__ = "reviewers"
    reviewer_id = Column(Integer, primary_key=True)
    name = Column(String)

#every saved version of the transcription prompt (kind "prompt") and of each page type's template; the newest is used
class InstructionVersion(Base):
    __tablename__ = "instruction_versions"
    version_id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    sha256 = Column(String, nullable=False) #of the body as UTF-8, as the pipeline's reuse check hashes it
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=True) #None: version 1, from the files
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now()) #UTC

#work queued by the API for backend/worker.py, oldest first: a bundle's pipeline run, one page read again as a page type,
#or training page sorting
class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint("status IN ('waiting', 'running', 'done', 'failed')", name="status"),
                      CheckConstraint("kind IN ('bundle', 'page', 'train')", name="kind"))
    job_id = Column(Integer, primary_key=True, autoincrement=True)
    base_revision = Column(Integer, nullable=True)
    transcription_model = Column(String, nullable=True)
    transcription_provider = Column(String, nullable=True)
    transcription_effort = Column(String, nullable=True)
    kind = Column(String, nullable=False, default="bundle", server_default="bundle")
    pdf = Column(String, nullable=True) #a bundle job's PDF
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), nullable=True) #a page job's page...
    page_type = Column(String, ForeignKey("page_types.name"), nullable=True) #...and the type to read it as
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=True) #who asked for a page or training job
    status = Column(String, nullable=False, default="waiting", server_default="waiting")
    step = Column(String, nullable=True) #step the worker is on
    done_pages = Column(Integer, nullable=False, default=0, server_default="0")
    total_pages = Column(Integer, nullable=False, default=0, server_default="0")
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=True, server_default=func.now(), onupdate=func.now()) #UTC, set on every change

#page sorting retrained from the review screen; new bundles are sorted by the active one, or the shipped model if none is
class SortingModel(Base):
    __tablename__ = "sorting_models"
    model_id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String, nullable=True) #its weights; None: it failed the check, so it wasn't kept
    page_types = Column(Text, nullable=False) #what it sorts into, comma-separated
    pages = Column(Integer, nullable=False) #the check: each page sorted by a model that never saw it...
    answered = Column(Integer, nullable=False) #...how many it answered (the rest go to review)...
    wrong = Column(Integer, nullable=False) #...and how many of those wrongly
    passed = Column(Boolean, nullable=False) #no wrong answers, and enough answered
    active = Column(Boolean, nullable=False, default=False, server_default=false())
    note = Column(Text, nullable=True) #page types left out for too few confirmed pages
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=func.now()) #UTC

class Edit(Base):
    __tablename__ = "edits"
    __table_args__ = (
        ForeignKeyConstraint(["page_id", "field_title"], ["fields.page_id", "fields.field_title"], ondelete="CASCADE"),
        ForeignKeyConstraint(["page_id", "resident_field_title", "resident_no"],
                             ["resident_fields.page_id", "resident_fields.resident_field_title", "resident_fields.resident_no"],
                             ondelete="CASCADE"),
        ForeignKeyConstraint(["page_id", "child_residence", "child_no"],
                             ["other_children.page_id", "other_children.residence", "other_children.child_no"],
                             ondelete="CASCADE"),
        ForeignKeyConstraint(["page_id", "annotation_no"], ["annotations.page_id", "annotations.annotation_no"],
                             ondelete="CASCADE"),
        #an edit targets exactly one of: field, resident field, child, annotation
        CheckConstraint("(field_title IS NOT NULL) + (resident_field_title IS NOT NULL) + (child_no IS NOT NULL)"
                        " + (annotation_no IS NOT NULL) = 1 AND (resident_field_title IS NULL) = (resident_no IS NULL)"
                        " AND (child_residence IS NULL) = (child_no IS NULL)",
                        name="exclusivity"),
    )
    edit_id = Column(Integer, primary_key=True, autoincrement=True)
    edit_text = Column(Text, nullable=True)
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=True)
    time = Column(DateTime, nullable=True)
    page_id = Column(String, nullable=False)
    field_title = Column(String, nullable=True)
    resident_field_title = Column(String, nullable=True)
    resident_no = Column(Integer, nullable=True)
    child_residence = Column(String, nullable=True)
    child_no = Column(Integer, nullable=True)
    annotation_no = Column(Integer, nullable=True)

class OtherChild(Base):
    __tablename__ = "other_children"
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), primary_key=True)
    residence = Column(String, primary_key=True) #died or living_elsewhere
    child_no = Column(Integer, primary_key=True)
    text_raw = Column(String)

class Annotation(Base):
    __tablename__ = "annotations"
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), primary_key=True)
    annotation_no = Column(Integer, primary_key=True)
    text_raw = Column(String, nullable=True)
    location = Column(String, nullable=True)
    area = Column(String, nullable=True) #a name in pipeline/transcribe/areas.json for the page type
    region = Column(String, nullable=True) #JSON {"x", "y", "width", "height"}: a closer box than the area's, shown instead of it

# Audit trail; moving a page never rewrites its extracted fields or reviews
class PageMove(Base):
    __tablename__ = "page_moves"
    move_id = Column(Integer, primary_key=True)
    page_id = Column(String, ForeignKey("pages.page_id"), nullable=False)
    from_survey = Column(String, nullable=True)
    to_survey = Column(String, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=False)
    reason = Column(Text, nullable=False, default="")
    time = Column(DateTime, nullable=False, server_default=func.now())

# Snapshot before reclassification or replacement, including saved edits.
class PageVersion(Base):
    __tablename__ = "page_versions"
    version_id = Column(Integer, primary_key=True)
    page_id = Column(String, ForeignKey("pages.page_id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.reviewer_id"), nullable=False)
    action = Column(String, nullable=False)
    snapshot = Column(Text, nullable=False)
    time = Column(DateTime, nullable=False, server_default=func.now())

# Settings edited in the app and shared with the team through the committed db; key like "transcription.model"
class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=True, server_default=func.now(), onupdate=func.now())
