# Signal Check

A small Flask app that searches recent fact-checks and related news.

## Run locally

1. Install the packages with `pip install -r requirements.txt`.
2. Run `python app.py` from this directory and open `http://127.0.0.1:5000`.

No API key is required. When a claim is submitted, the app downloads recent
articles from [The Guardian World RSS](https://www.theguardian.com/world/rss)
and [Al Jazeera RSS](https://www.aljazeera.com/xml/rss/all.xml),
[Deutsche Welle](https://rss.dw.com/xml/rss-en-all),
[France 24](https://www.france24.com/en/rss),
[CNBC](https://www.cnbc.com/id/100003114/device/rss/rss.html), and
[Euronews](https://www.euronews.com/rss?format=mrss&level=theme&name=news).
It also searches the query-specific
[Google News RSS feed](https://news.google.com/rss/search?q=your+search+terms&hl=en-US&gl=US&ceid=US:en).
The first 500 characters of the submitted claim are sent to Google News to
retrieve search results. The app compares results against the query locally and
other publishers' RSS feed content stays local. Results show headlines,
publisher names, dates, and links rather than reproducing feed descriptions.

Fact-check lookup separately uses the
[Snopes fact-check RSS feed](https://www.snopes.com/fact-check/feed/).

Matching items are evidence to review, not a truth verdict. A missing match does
not establish that a claim is true or false. Snopes is currently the only
configured fact-check feed, and news coverage is limited to recent entries from
the configured publishers. Feeds are fetched concurrently; failures are shown
in the app rather than reported as a no-match result. Publisher terms apply.
