from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

import os.path

DATABASE_FILE = 'sqlite.db'

Base = declarative_base()

class Article(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    link = Column(String(length=300))
    source = Column(String(length=10))
    seen = Column(DateTime)
    versions = relationship('Version', back_populates='article', order_by='Version.seen')
    tweet_id = Column(Integer)

    def __repr__(self):
        return "<Article(id='%s', link='%s', source='%s')>" % (self.id, self.link, self.source)


class Version(Base):
    __tablename__ = 'versions'

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id'))
    article = relationship('Article', back_populates='versions')
    title = Column(Text)
    intro = Column(Text)
    seen = Column(DateTime)

    def __repr__(self):
        return "<Version(article_id='%s', title='%s')>" % (self.article_id, self.title)


engine = create_engine('sqlite:///{}'.format(DATABASE_FILE))
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
