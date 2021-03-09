import datetime
import dateutil.parser
import json
import os
import re
import time

import feedparser
import telegram


def escape(s):
    return re.sub(r"""([][*_`.+?^$(){}\-])""", r"\\\1", s)


def main():
    # Switch to script directory first
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with open("config.json", "r") as f:
        CONFIG = json.load(f)
    bot = telegram.Bot(token=CONFIG['telegram_token'])

    DATA = {
        'last_delivered': dateutil.parser.parse("1970-01-01T00:00:00Z"),
    }
    if os.path.isfile("data.json"):
        with open("data.json", "r") as f:
            DATA = json.load(f)

    feed_list = CONFIG['feeds']
    last_delivered = dateutil.parser.parse(DATA['last_delivered'])
    queue = []

    for item in feed_list:
        feeds = feedparser.parse(item['url'])

        for feed in feeds.entries:
            feed_time = dateutil.parser.parse(feed['published'])
            if feed_time > last_delivered:
                feed['time'] = feed_time
                queue.append((item['name'], feed))

    queue.sort(key=lambda x: x[1]['time'])
    if queue:
        for name, feed in queue:
            author = feed['authors'][0]
            if author['name'] == "github-actions[bot]":
                continue
            message = f"*\\[{escape(name)}\\]* {escape(feed['title'])}" \
                      f" \\([{escape(author['name'])}]({feed['link']})\\)"
            bot.send_message(chat_id=CONFIG['chat_id'],
                             text=message,
                             parse_mode="MarkdownV2",
                             disable_web_page_preview=True)
            time.sleep(1)
        DATA['last_delivered'] = queue[-1][1]['time'].isoformat()

    with open("data.json", "w") as f:
        json.dump(DATA, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
