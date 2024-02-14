#utf-8
from botasaurus import *
from datetime import datetime, timedelta
import requests
import json

webhook_url = 'YOUR_WEBHOOK_URL'  # Replace with your Discord webhook URL

# Configuration for storing sent articles
sent_articles_filename = "sent_articles.json"   # Filename to store sent articles
sent_articles_duration_in_days = 10             # Duration in days to keep the articles before removing them

base_url = 'https://www.suedkurier.de'
region_url = '/region/kreis-konstanz/singen/'

## Helper functions for saving sent articles
def load_sent_articles():
    """
    Loads sent articles from a JSON file. If the file does not exist,
    it returns an empty list.
    """
    try:
        with open(sent_articles_filename, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        # Create an empty list if the file does not exist
        return []

def save_sent_article(article_url):
    """
    Saves a new article URL to the JSON file with the current date.
    """
    sent_articles = load_sent_articles()
    current_date = datetime.now().strftime("%Y-%m-%d")
    sent_articles.append({"url": article_url, "date": current_date})
    with open(sent_articles_filename, "w") as file:
        json.dump(sent_articles, file, indent=4)

def article_already_sent(article_url):
    """
    Checks if an article URL is already in the sent articles list.
    """
    sent_articles = load_sent_articles()
    urls = [article['url'] for article in sent_articles]
    if article_url in urls:
        print(f"Article already sent: {article_url}")
        return True
    else:
        print(f"New article to send: {article_url}")
        return False

def remove_old_articles():
    """
    Removes articles older than a specified number of days from the JSON file.
    Only prints a message if articles were actually removed.
    """
    sent_articles = load_sent_articles()
    cutoff_date = datetime.now() - timedelta(days=sent_articles_duration_in_days)
    # Filter articles to keep those newer than the cutoff date
    updated_articles = [article for article in sent_articles if datetime.strptime(article['date'], "%Y-%m-%d") > cutoff_date]
    
    # Check if any articles were removed
    if len(sent_articles) != len(updated_articles):
        # Only print the message if articles have been removed
        print(f"Removed old articles older than {sent_articles_duration_in_days} days.")
        
        # Save the updated list of articles
        with open(sent_articles_filename, "w") as file:
            json.dump(updated_articles, file, indent=4)
## End of helper functions

@request(use_stealth=True)
def get_article_image(request: AntiDetectRequests, article_url):
    """
    Attempts to fetch the main image URL for a specific article.
    
    Args:
        request: A special object provided by botasaurus for making web requests.
        article_url: URL of the article to scrape the image from.
    
    Returns:
        The URL of the main image if found; otherwise, None.
    """
    # Parses the article's page to search for the main image.
    soup = request.bs4(article_url)
    image_element = soup.select_one('article section.row.fullscreen-img div.col-12 figure img')
    # Constructs the full URL for the image if it's found.
    if image_element:
        image_src = image_element['src']
        image_url = image_src if image_src.startswith('http') else f"{base_url}{image_src}"
        return image_url
    return None

@request(use_stealth=True)
def scrape_heading_task(request: AntiDetectRequests, data):
    """
    Scrapes articles from a specified section of the website, collecting various details.
    
    Args:
        request: A special object for making web requests with anti-detection features.
        data: Additional data for the request; not used in this function.
    
    Returns:
        A dictionary containing sorted articles based on their publication dates.
    """
    soup = request.bs4(f'{base_url}{region_url}')
    articles = soup.select('article')
    articles_data = []
    
    for article in articles:
        headline_element = article.select_one('.headline')
        headline_text = headline_element.get_text(strip=True) if headline_element else None
        if not headline_text:
            continue  # Skips articles without headlines.
        
        time_element = article.select_one('time')
        publication_date = time_element['datetime'] if time_element else None
        if not publication_date:
            continue  # Skips articles without publication dates.
        
        article_url_element = article.select_one('a[href]')
        article_url = f"{base_url}{article_url_element['href']}" if article_url_element else None

        if not article_url or article_already_sent(article_url):
            continue  # Skip articles without URL or already sent
        
        image_url = get_article_image(article_url)  # Fetches the image URL.
        
        article_summary_element = article.select_one('.article-summary')
        article_text = article_summary_element.get_text(strip=True) if article_summary_element else None
        
        articles_data.append({
            "headline": headline_text,
            "publication_date": publication_date,
            "url": article_url,
            "image_url": image_url,
            "text": article_text
        })

    return {"articles": sorted(articles_data, key=lambda x: x['publication_date'], reverse=True)}

def send_to_discord_webhook(article):
    """
    Posts an article's data to a Discord channel via a specified webhook.
    
    Args:
        article: A dictionary containing the article's data.
    """
    headers = {'Content-Type': 'application/json'}
    # Prepares the data payload for Discord.
    data = {
        "embeds": [{
            "title": article['headline'],
            "url": article['url'],
            "color": 5814783,
            "description": article['text'],
            "image": {"url": article['image_url']},
            "author": {
                "name": "Südkurier",
                "url": "https://www.suedkurier.de",
                "icon_url": "https://abonnieren.suedkurier.de/wp-content/uploads/SK_Icon_blau-1-1.png"
            },
            "footer": {"text": "Umgebung - Singen (Hohentwiel)"},
            "timestamp": article['publication_date']
        }]
    }
    # Sends the data to the Discord webhook.
    response = requests.post(webhook_url, json=data, headers=headers)
    try:
        response.raise_for_status()
        print("Message successfully sent to Discord.")
    except requests.exceptions.HTTPError as e:
        print(f"Error sending message: {e}")
        if response.text:
            print(response.json())

if __name__ == "__main__":
    # Initiate the web scraping task
    articles_data_sorted = scrape_heading_task()

    for article in articles_data_sorted['articles']:
        send_to_discord_webhook(article)
        remove_old_articles()
        save_sent_article(article['url'])
