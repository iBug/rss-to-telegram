import datetime
import dateutil.parser
import logging
import os
import re
import sys
import threading
import time
from collections import defaultdict

import feedparser
import requests
import telegram
import yaml


CONFIG_FILE = "config.yaml"
DATA_FILE = "data.yaml"
EXCLUDE_AUTHORS = ["github-actions[bot]"]
DEFAULT_TIME = "1970-01-01T00:00:00Z"
NOW_S = datetime.datetime.now(datetime.UTC).isoformat()


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s %(module)s - %(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def escape(s):
    return telegram.utils.helpers.escape_markdown(s, 2)


def fetch_feed(name, source, last_delivered, output):
    try:
        resp = requests.get(source, timeout=10)
        resp.raise_for_status()
        feeds = feedparser.parse(resp.text)

        for feed in feeds.entries:
            feed_time = dateutil.parser.parse(feed.get('published', feed.get('updated')))
            if not feed_time.tzinfo:
                feed_time = feed_time.replace(tzinfo=datetime.UTC)
            if feed_time > last_delivered:
                feed['time'] = feed_time
                output.append((name, feed))
    except Exception:
        exc_type, exc_obj, _ = sys.exc_info()
        logging.error("{}: {}".format(exc_type.__name__, exc_obj))


def main():
    setup_logging()

    # Switch to script directory first
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with open(CONFIG_FILE, "r") as f:
        CONFIG = yaml.safe_load(f)
    bot = telegram.Bot(token=CONFIG['telegram_token'])

    DATA = {
        'last_delivered': defaultdict(lambda: DEFAULT_TIME)
    }
    if os.path.isfile(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            DATA = yaml.safe_load(f)
            old_record = DATA['last_delivered']
            if isinstance(old_record, str):
                DATA['last_delivered'] = defaultdict(lambda: old_record)
            elif isinstance(old_record, dict):
                DATA['last_delivered'] = defaultdict(lambda: DEFAULT_TIME, old_record)
            else:
                raise TypeError(f"Wrong type {DATA['last_delivered'].__class__} for last_delivered")

    feed_list = CONFIG['feeds']
    queue = []
    threads = []

    for item in feed_list:
        logging.info(f"Working on {item['name']}")
        last_delivered = dateutil.parser.parse(DATA['last_delivered'][item['name']])
        args = [item['name'], item['url'], last_delivered, queue]
        if CONFIG.get('parallel_fetch'):
            th = threading.Thread(target=fetch_feed, args=args)
            th.start()
            threads.append(th)
        else:
            fetch_feed(*args)
    if CONFIG.get('parallel_fetch'):
        for th in threads:
            th.join()

    if queue:
        queue.sort(key=lambda x: x[1]['time'])
        for name, feed in queue:
            author = feed.get('authors', [{'name': "None"}])[0]
            if author['name'] in EXCLUDE_AUTHORS:
                continue
            try:
                message = f"[*\\[{escape(name)}\\]*]({feed['link']}) {escape(feed['title'])}" \
                          f" \\(by _{escape(author['name'])}_\\)"
                bot.send_message(chat_id=CONFIG['chat_id'],
                                 text=message,
                                 parse_mode="MarkdownV2",
                                 disable_web_page_preview=True)
                if dateutil.parser.parse(DATA['last_delivered'][name]) < feed['time']:
                    DATA['last_delivered'][name] = feed['time'].isoformat()
                time.sleep(1)
            except Exception:
                exc_type, exc_obj, _ = sys.exc_info()
                logging.error("{}: {}".format(exc_type.__name__, exc_obj))

    DATA['last_delivered'] = dict(DATA['last_delivered'])
    with open(DATA_FILE, "w") as f:
        yaml.dump(DATA, f, indent=2, default_flow_style=False)


if __name__ == '__main__':
    main()
