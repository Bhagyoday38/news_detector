import os

from flask import Flask, render_template, request

from fact_check_service import (
    NEWS_SOURCE_NAMES,
    SOURCE_NAMES,
    find_related_fact_checks,
    find_related_news,
)


app = Flask(__name__)
MAX_ARTICLE_LENGTH = 20_000


def _render_page(**context):
    page_context = {
        "article": "",
        "error": None,
        "search_result": None,
        "news_result": None,
        "source_names": SOURCE_NAMES,
        "news_source_names": NEWS_SOURCE_NAMES,
        "max_article_length": MAX_ARTICLE_LENGTH,
    }
    page_context.update(context)
    return render_template("index.html", **page_context)


@app.route("/")
def home():
    return _render_page()


@app.route("/predict", methods=["POST"])
def predict():
    article = request.form.get("news_article", "").strip()
    if not article:
        return _render_page(
            error="Paste a claim, headline, or article to search for related news and fact-checks."
        )
    if len(article) > MAX_ARTICLE_LENGTH:
        return _render_page(
            article=article[:MAX_ARTICLE_LENGTH],
            error=f"Please keep the article under {MAX_ARTICLE_LENGTH:,} characters.",
        )

    return _render_page(
        article=article,
        search_result=find_related_fact_checks(article),
        news_result=find_related_news(article),
    )


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
