from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Table,
    Column,
    Integer,
    String,
    DateTime,
    Float,
    Text,
    ForeignKey,
    Boolean,
)

Base = declarative_base()

CLAIM_NAME_LENGTH = 256
CLAIM_HASH_LENGTH = 96
TITLE_LENGTH = 512
KEY_LENGTH = 512  # Might as well


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)

    manuscripts = relationship("Manuscript", back_populates="article")
    base_claim_name = Column(String(CLAIM_NAME_LENGTH))
    channel_name = Column(String(CLAIM_NAME_LENGTH))

    encryption_passphrase = Column(String(1024))
    review_passphrase = Column(String(1024))

    reviewed = Column(Boolean())
    revision = Column(Integer())

    review_server_id = Column(Integer, ForeignKey("servers.id"))
    review_server = relationship("Server")

    @property
    def title(self):
        return self.manuscripts[-1].title

    @property
    def abstract(self):
        return self.manuscripts[-1].abstract

    @property
    def authors(self):
        return self.manuscripts[-1].authors

    @property
    def tags(self):
        return self.manuscripts[-1].tags


class Manuscript(Base):
    __tablename__ = "manuscripts"

    id = Column(Integer, primary_key=True)
    claim_name = Column(String(CLAIM_NAME_LENGTH))
    bid = Column(Float(precision=8))
    file_path = Column(String(512))
    submission_date = Column(DateTime())
    txid = Column(String(40))
    txhash = Column(String(CLAIM_HASH_LENGTH))

    title = Column(String(TITLE_LENGTH))
    abstract = Column(Text())
    authors = Column(Text())
    tags = Column(String(1024))  # Tags stored as text

    article = relationship("Article")
    article_id = Column(Integer, ForeignKey("articles.id"))


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)

    # The reviewed manuscript will obviously not be by the user and thus not in the database.
    # The metadata is thus kept here.
    submission_title = Column(String(TITLE_LENGTH))
    submission_claim_name = Column(
        String(CLAIM_NAME_LENGTH)
    )  # Will indicate the revision/version number
    submission_channel_name = Column(String(CLAIM_NAME_LENGTH))
    submission_authors = Column(Text())
    submission_date = Column(DateTime())

    review_date = Column(DateTime())
    review_text = Column(Text())
    review_signature = Column(Text())  # String
    review_signature_timestamp = Column(Text())  # String

    server_id = Column(Integer, ForeignKey("servers.id"))
    server = relationship("Server")

    @property
    def is_sent(self):
        if self.review_date:
            return True
        return False


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True)

    name = Column(String(512))
    channel_name = Column(String(512))
    url = Column(String(512))
    submitted_reviews = relationship("Review", back_populates="server")

    public_key = Column(String(KEY_LENGTH))
    reviewed_articles = relationship("Article", back_populates="review_server")
