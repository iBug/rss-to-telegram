import datetime
import dateutil.parser
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict

import feedparser
import telegram


EXCLUDE_AUTHORS = ["github-actions[bot]"]
DEFAULT_TIME = "1970-01-01T00:00:00Z"
NOW_S = datetime.datetime.now(datetime.UTC).isoformat()


def escape(s):
    return telegram.utils.helpers.escape_markdown(s, 2)


def fetch_feed(name, source, last_delivered, output):
    feeds = feedparser.parse(source)

    for feed in feeds.entries:
        feed_time = dateutil.parser.parse(feed.get('published', feed.get('updated')))
        if not feed_time.tzinfo:
            feed_time = feed_time.replace(tzinfo=datetime.UTC)
        if feed_time > last_delivered:
            feed['time'] = feed_time
            output.append((name, feed))


def main():
    # Switch to script directory first
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with open("config.json", "r") as f:
        CONFIG = json.load(f)
    bot = telegram.Bot(token=CONFIG['telegram_token'])

    DATA = {
        'last_delivered': defaultdict(lambda: DEFAULT_TIME)
    }
    if os.path.isfile("data.json"):
        with open("data.json", "r") as f:
            DATA = json.load(f)
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
        print(f"Working on {item['name']}")
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
                message = f"*\\[{escape(name)}\\]* {escape(feed['title'])}" \
                          f" \\([{escape(author['name'])}]({feed['link']})\\)"
                bot.send_message(chat_id=CONFIG['chat_id'],
                                 text=message,
                                 parse_mode="MarkdownV2",
                                 disable_web_page_preview=True)
                if dateutil.parser.parse(DATA['last_delivered'][name]) < feed['time']:
                    DATA['last_delivered'][name] = feed['time'].isoformat()
                time.sleep(1)
            except Exception:
                exc_type, exc_obj, _ = sys.exc_info()
                print("{}: {}".format(exc_type.__name__, exc_obj))

    DATA['last_delivered'] = dict(DATA['last_delivered'])
    with open("data.json", "w") as f:
        json.dump(DATA, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
