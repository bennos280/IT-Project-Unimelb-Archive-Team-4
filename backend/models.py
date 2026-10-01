from sqlalchemy import Column, Integer, String, Text, Numeric, LargeBinary, ForeignKey, DateTime
from database import Base


class Bundle(Base):
    __tablename__ = "bundles"
    bundle_id = Column(String, primary_key=True)
    source_pdf = Column(String, nullable=False)
    import_status = Column(Integer, nullable=False, default=0)

class Survey(Base):
    __tablename__ = "surveys"
    survey_id = Column(String, primary_key=True)
    bundle_id = Column(String, ForeignKey("bundles.bundle_id", ondelete="CASCADE"), nullable=False)

class Category(Base):
    __tablename__ = "categories"
    category = Column(String, primary_key=True)

class Page(Base):
    __tablename__ = "pages"
    page_id = Column(String, primary_key=True)
    import_path = Column(String, nullable=False)
    img = Column(LargeBinary, nullable=True)
    engine = Column(String, nullable=True)
    model = Column(String, nullable=True)
    effort = Column(String, nullable=True)
    runtime = Column(Numeric, nullable=True)
    revision_no = Column(Integer, default=0)
    survey_id = Column(String, ForeignKey("surveys.survey_id", ondelete="CASCADE"), nullable=True)
    bundle_id = Column(String, ForeignKey("bundles.bundle_id", ondelete="CASCADE"), nullable=False)
    category = Column(String, ForeignKey("categories.category"), nullable=False)

class Flag(Base):
    __tablename__ = "flags"
    flag_type = Column(String, primary_key=True)

class Field(Base):
    __tablename__ = "fields"
    page_id = Column(String, ForeignKey("pages.page_id", ondelete="CASCADE"), primary_key=True, nullable=False)
    field_title = Column(String, primary_key=True, nullable=False)
    text_raw = Column(Text, nullable=True)
    decoded_value = Column(Text, nullable=True)
    flag_type = Column(String, ForeignKey("flags.flag_type"), nullable=True)

class Reviewer(Base):
    __tablename__ = "reviewers"
    reviewer_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Edit(Base):
    __tablename__ = "edits"
    edit_id = Column(Integer, primary_key=True, autoincrement=True)
    edit_text = Column(Text, nullable=True)
    reviewer_id = Column(Integer, nullable=True)
    time = Column(DateTime, nullable=True)
    page_id = Column(String, nullable=False)
    field_title = Column(String, nullable=True)
    resident_field_title = Column(String, nullable=True)
    resident_no = Column(Integer, nullable=True)
    child_no = Column(Integer, nullable=True)
    annotation_no = Column(Integer, nullable=True)

class OtherChild(Base):
    __tablename__ = "other_children"
    page_id = Column(String, primary_key=True)
    child_no = Column(Integer, primary_key=True)
    residence = Column(String)
    text_raw = Column(String)
    flag_type = Column(String)

class Annotation(Base):
    __tablename__ = "annotations"
    page_id = Column(String, primary_key=True)
    annotation_no = Column(Integer, primary_key=True)
    text_raw = Column(String, nullable=True)
    location = Column(String, nullable=True)
    flag_type = Column(String)
