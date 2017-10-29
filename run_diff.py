# -*- coding: utf-8 -*-

import hashlib
import logging
import os
import requests
import sys
import time
import tweepy

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy import and_
from database import Session, Article, Version
from PIL import Image
from simplediff import html_diff
from selenium import webdriver
from html.parser import HTMLParser

logging.basicConfig(filename='log.txt',
                    format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)

PHANTOMJS_PATH = os.environ['PHANTOMJS_PATH']


def rss_from_internet():
    req = requests.get('http://www.abc.com.py/rss.xml')
    text = req.text
    return text


def rss_from_file(filename):
    with open(filename, 'r') as f:
        return f.read()


def valid_rss(supposed_rss):
    return 'incapsula' not in supposed_rss


def process_rss_entries(rss_text):
    import xml.etree.ElementTree as ET

    tree = ET.fromstring(rss_text)
    parser = HTMLParser()

    ret = []
    for item in tree.iter('item'):
        guid = item.find('guid').text

        if '/730am/' in guid or guid.endswith('.com.py/'):
            continue

        title = item.find('title').text
        description = item.find('description').text

        bs = BeautifulSoup(description, 'html.parser')

        clean_description = bs.text
        clean_description = parser.unescape(clean_description)
        clean_description = clean_description.strip()


        ret.append({ 'title': title, 'intro': clean_description, 'link': guid, 'source': 'abc'})

    return ret


def generate_diff(old, new):
    if len(old) == 0 or len(new) == 0:
        logging.info('Old or New empty')
        return False
    new_hash = hashlib.sha224(new.encode('utf8')).hexdigest()
    logging.info(html_diff(old, new))
    html = """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="./css/styles.css">
      </head>
      <body>
      <p>
      {}
      </p>
      </body>
    </html>
    """.format(html_diff(old, new))
    with open('tmp.html', 'w') as f:
        f.write(html)

    driver = webdriver.PhantomJS(
        executable_path=PHANTOMJS_PATH + '/phantomjs')
    driver.get('tmp.html')
    e = driver.find_element_by_xpath('//p')
    start_height = e.location['y']
    block_height = e.size['height']
    end_height = start_height
    start_width = e.location['x']
    block_width = e.size['width']
    end_width = start_width
    total_height = start_height + block_height + end_height
    total_width = start_width + block_width + end_width
    timestamp = str(int(time.time()))
    driver.save_screenshot('./tmp.png')
    img = Image.open('./tmp.png')
    img2 = img.crop((0, 0, total_width, total_height))
    if int(total_width) > int(total_height * 2):
        background = Image.new('RGBA', (total_width, int(total_width / 2)),
                               (255, 255, 255, 0))
        bg_w, bg_h = background.size
        offset = (int((bg_w - total_width) / 2),
                  int((bg_h - total_height) / 2))
    else:
        background = Image.new('RGBA', (total_width, total_height),
                               (255, 255, 255, 0))
        bg_w, bg_h = background.size
        offset = (int((bg_w - total_width) / 2),
                  int((bg_h - total_height) / 2))
    background.paste(img2, offset)
    filename = timestamp + new_hash
    exported_filename = './output/' + filename + '.png'
    background.save(exported_filename)

    return True, exported_filename


def create_article_version_if_needed(article_dict):
    previous_version = None
    current_version = None

    current_datetime = datetime.now()
    article = session.query(Article).filter_by(link=article_dict['link']).first()

    if not article:
        article = Article()
        article.link = article_dict['link']
        article.source = article_dict['source']

    if len(article.versions) > 0:
        previous_version = article.versions[len(article.versions) - 1]
        if previous_version.title == article_dict['title'] and previous_version.intro == article_dict['intro']:
            return None, None

    article.seen = current_datetime
    current_version = Version()
    current_version.title = article_dict['title']
    current_version.intro = article_dict['intro']
    current_version.seen = current_datetime
    current_version.article = article
    session.add(current_version)
    session.commit()

    return previous_version, current_version

class Twitter:
    def __init__(self):
        tw_consumer_key = os.environ['TWITTER_CONSUMER_KEY']
        tw_consumer_secret = os.environ['TWITTER_CONSUMER_SECRET']
        tw_access_token = os.environ['TWITTER_ACCESS_TOKEN']
        tw_access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

        auth = tweepy.OAuthHandler(tw_consumer_key, tw_consumer_secret)
        auth.secure = True
        auth.set_access_token(tw_access_token, tw_access_token_secret)
        self.twitter = tweepy.API(auth)

    def media_upload(self, filename):
        try:
            response = self.twitter.media_upload(filename)
        except:
            print (sys.exc_info()[0])
            logging.exception('Media upload')
            return False
        return response.media_id_string

    def tweet_with_media(self, text, images, reply_to=None):
        try:
            if reply_to is not None:
                tweet_id = self.twitter.update_status(
                    status=text, media_ids=images,
                    in_reply_to_status_id=reply_to)
            else:
                tweet_id = self.twitter.update_status(
                    status=text, media_ids=images)
        except:
            logging.exception('Tweet with media failed')
            print (sys.exc_info()[0])
            return False
        return tweet_id

    def tweet_text(self, text):
        try:
            tweet_id = self.twitter.update_status(status=text)
        except:
            logging.exception('Tweet text failed')
            print (sys.exc_info()[0])
            return False
        return tweet_id

    def tweet(self, text, article, prv_text, cur_text):

        result, image_filename = generate_diff(prv_text, cur_text)
        if not result:
            logging.error(' some problem when creating the diff... exiting')
            return

        image = self.media_upload(image_filename)

        logging.info('Media ready with ids: %s', image)
        logging.info('Text to tweet: %s', text)
        logging.info('Article id: %s', article.id)

        reply_to = article.tweet_id

        if reply_to is None:
            logging.info('Tweeting url: %s', article.link)

            tweet = self.tweet_text(article.link)
            reply_to = tweet.id

        logging.info('Replying to: %s', reply_to)

        tweet = self.tweet_with_media(text, [image], reply_to)

        logging.info('Id to store: %s', tweet.id)

        # update latest tweet in db
        article.tweet_id = tweet.id

        session.add(article)
        session.commit()
    

if __name__ == '__main__':
    session = Session()
    twitter = Twitter()

    rss = rss_from_internet()

    if not valid_rss(rss):
        logging.error('Not a valid RSS obtained, exiting....')
        logging.error(rss)
        sys.exit(1)

    logging.info('obtained valid RSS')

    entries = process_rss_entries(rss)
    for article_dict in entries:
        previous_version, current_version = create_article_version_if_needed(article_dict)
        if previous_version is None or current_version is None:
            continue

        logging.info('new version found')

        if previous_version.title != current_version.title:
            logging.info('Title change...')
            twitter.tweet('Cambio en el título', previous_version.article, previous_version.title, current_version.title)
        if previous_version.intro != current_version.intro:
            logging.info('Intro change...')
            twitter.tweet('Cambio en la bajada', previous_version.article, previous_version.intro, current_version.intro)


#### FIXME agregar el filtro de seen <= (ahora - x horas)
###for db_article in database_list:
###    found, article = get_article_from_link(db_article.link)
###    if not found:
###        continue
###    create_article_version_if_needed(article)
