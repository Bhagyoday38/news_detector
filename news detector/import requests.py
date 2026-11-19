import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

# Send request to Google News
url = "https://news.google.com/topstories"
response = requests.get(url, timeout=15)
response.raise_for_status()

# Parse HTML content using BeautifulSoup
soup = BeautifulSoup(response.text, 'html.parser')

# Find all news article elements
articles = soup.find_all('article')

# Create a list to store news article data
news_data = []

# Loop through each article element
for article in articles:
    # Extract article title
    title_tag = article.find('h3')
    title = title_tag.text.strip() if title_tag else ""

    # Extract article link
    link_tag = article.find('a')
    link = requests.compat.urljoin(url, link_tag['href']) if link_tag else ""

    # Extract article description (as text)
    description_tag = article.find('span', class_='IsZvec')
    description = description_tag.text.strip() if description_tag else ""

    # Combine title and description into 'text' for the dataset
    text = f"{title} {description}".strip()

    # Append article data to the list
    news_data.append({
        "title": title,
        "link": link,
        "text": text,
        "label": ""
    })

# Preserve the dataset and avoid assigning unverified truth labels.
file_path = Path(__file__).resolve().parent.parent / "news_data.csv"
columns = ["title", "link", "text", "label"]
new_articles = pd.DataFrame(news_data, columns=columns)
if file_path.exists():
    existing_articles = pd.read_csv(file_path).reindex(columns=columns)
    updated_df = pd.concat([existing_articles, new_articles], ignore_index=True)
else:
    updated_df = new_articles

updated_df = updated_df.fillna('').drop_duplicates(
    subset=["title", "link"],
    keep="first",
)
updated_df.to_csv(file_path, index=False, columns=columns)
print(f"Dataset updated with {len(new_articles)} unverified articles: {file_path}")
