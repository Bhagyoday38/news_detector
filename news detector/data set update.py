import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from pathlib import Path


OUTPUT_PATH = Path(__file__).resolve().parent.parent / 'news_data.csv'
DATASET_COLUMNS = ['title', 'link', 'text', 'label']

# List of top news websites you want to scrape, including Indian sources
urls = [
    'https://www.bbc.com/news',
    'https://edition.cnn.com/',
    'https://www.nytimes.com/section/world',
    'https://www.theguardian.com/world',
    'https://www.reuters.com/news/world',
    'https://www.aljazeera.com/news/',
    'https://www.huffpost.com/news/world',
    'https://www.usatoday.com/news/world/',
    'https://www.nbcnews.com/world',
    'https://www.foxnews.com/world',
    'https://www.abcnews.go.com/International',
    # Indian news websites
    'https://timesofindia.indiatimes.com/',
    'https://www.thehindu.com/',
    'https://www.ndtv.com/',
    'https://www.indiatoday.in/',
    'https://www.hindustantimes.com/',
    'https://www.firstpost.com/',
    'https://www.moneycontrol.com/news/',
    'https://www.cnbctv18.com/news/',
    'https://www.mintlive.com/',
    'https://www.sportmonks.com/',
    'https://www.espn.in/',
    'https://sports.ndtv.com/',
    'https://sportstar.thehindu.com/',
    'https://kheloindia.gov.in/',
    'https://www.cricbuzz.com/',
    'https://www.business-standard.com/'
]

# Function to scrape news articles
def scrape_news(url):
    articles = []
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Modify this based on the structure of the website (classes, tags, etc.)
        for article in soup.find_all('h3'):
            title = article.get_text(strip=True)
            anchor = article.find('a')
            if anchor and 'href' in anchor.attrs:  # Check if anchor exists and has an href
                link = anchor['href']
                if not link.startswith('http'):
                    link = requests.compat.urljoin(url, link)
                articles.append({
                    'title': title,
                    'link': link,
                    'text': '',
                    'label': ''
                })
                
    except requests.RequestException as e:
        print(f'Error scraping {url}: {e}')
    
    return articles

# Scrape each website
all_articles = []
for url in urls:
    articles = scrape_news(url)
    all_articles.extend(articles)
    print(f'Collected {len(articles)} articles from {url}.')
    time.sleep(2)  # To avoid overwhelming the server

# Keep collected articles separate from verified training labels.
new_articles = pd.DataFrame(all_articles, columns=DATASET_COLUMNS)
if OUTPUT_PATH.exists():
    existing_articles = pd.read_csv(OUTPUT_PATH).reindex(columns=DATASET_COLUMNS)
    updated_articles = pd.concat([existing_articles, new_articles], ignore_index=True)
else:
    updated_articles = new_articles

updated_articles = updated_articles.fillna('').drop_duplicates(
    subset=['title', 'link'],
    keep='first',
)
updated_articles.to_csv(OUTPUT_PATH, index=False, columns=DATASET_COLUMNS)

print(f'Total articles scraped: {len(all_articles)}')
print(f'Dataset updated: {OUTPUT_PATH}')
