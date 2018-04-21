import requests
import json
import sys

from time import sleep
from datetime import datetime

from urllib.error import HTTPError
from json.decoder import JSONDecodeError

import pandas as pd

from dataprocessing import get_replies, preprocess_comments_dataframe, preprocess_articles_dataframe

NYT_ARTICLE_API_URL = 'https://api.nytimes.com/svc/search/v2/articlesearch.json'
COMMENTS_URL = 'http://www.nytimes.com/svc/community/V3/requestHandler?callback=NYTD.commentsInstance.drawComments&method=&cmd=GetCommentsAll&url='

def get_dataset(ARTICLE_API_KEY, page_lower=0, page_upper=30, begin_date=None, end_date=None, 
                 max_comments=50000, sort='newest', query=None, filter_query=None, printout=True, 
                save=False, filename=None):
    '''Collects the comments on the articles of NYT by first scraping the 
    articles using NYT articles search API, calling on the customized function
    get_comments(url) to get comments on each article, processing the comments' 
    and articles' data and returning two pandas dataframes - one each for articles 
    and comments.'''
    
    params = {'api-key': ARTICLE_API_KEY}
    
    if page_lower<0:
        page_lower = 0
        if printout:
            print('Out of range value passed for page_lower. The page_lower parameter is set to 0.')
            print()
    
    if page_upper>200:
        page_upper = 200
        if printout:
            print('Out of range value passed for page_upper. The page_upper parameter is set to 199.')
            print()
        
    if (sort!='newest') & (sort!='oldest'):
        if printout:
            print('Invalid value passed for sort. The sort parameter is set to newest.')
            print()
    
    if sort=='oldest':
        if begin_date is None:
            begin_date = '20081031'   
    elif end_date is None:
        end_date = datetime.today().strftime('%Y%m%d')
        
    articles_list = []
    comments_df_list = []

    articles_df = pd.DataFrame()
    comments_df = pd.DataFrame()
        
    if begin_date: # Check begin_date is not None
        try:
            begin_date = pd.to_datetime(begin_date, errors='coerce').strftime('%Y%m%d')
        except:
            print("Error: Please try again with begin_date entered in the format %Y%m%d.")
            return articles_df, comments_df
        params['begin_date'] = begin_date 

    if end_date: # Check end_date is not None
        try:
            end_date = pd.to_datetime(end_date, errors='coerce').strftime('%Y%m%d')
        except:
            print("Error: Please try again with end_date entered in the format %Y%m%d.")
            return articles_df, comments_df
        params['end_date'] = end_date

    if query:
        params['q'] = query
        
    if filter_query:
        params['fq'] = filter_query

    params['sort'] = sort
    
    total_comments = 0
    
    HTTPErrorCount = 0
    
    for page in range(page_lower, page_upper):
        if total_comments < max_comments:
            params['page'] = page # Every page has 10 articles
            if printout:
                print("Page: ", page)
            try:
                # Using NYT API to get articles search data in json format
                js = requests.get(NYT_ARTICLE_API_URL, params=params).json()
                
                # Check whether API rate limit has exceeded
                if js.get('message'):
                    if printout:
                        print(js.get('message')+'for today. No more comments can be retrieved using the article search today, however the function get_comments can be used to retrieve further comments w/o limit if the URLs of the articles are given to the function manually.')
                    break
                
                # Check status to make sure data is retrieved correctly
                if js.get('status') == 'OK':
                    docs = js['response']['docs']
                    docs_length = len(docs)
                    if docs_length==0:
                        if printout:
                            print("No aricles found on page", page)
                        break
                    for i in range(docs_length):
                        if docs[i]['document_type'] != 'multimedia': # Ignore multimedia articles
                            article_url = docs[i]['web_url'] # Get the url for the article
                            
                            # Use the article url to get comments 
                            comments, error = get_comments(article_url, internal=True) 
                            number_comments = comments.shape[0]
                            total_comments += number_comments
                            if number_comments: # Check if the article has comments
                                article_id = docs[i]['_id']
                                article = docs[i]
                                articles_list.append(article)
                                comments['articleID'] = article_id
                                comments['sectionName'] = article.get('section_name', 'Unknown')
                                comments['newDesk'] = article.get('new_desk', 'Unknown')
                                comments['articleWordCount'] = article.get('word_count', 0)
                                comments['printPage'] = article.get('print_page', 0)
                                comments['typeOfMaterial'] = article.get('type_of_material', 'Unknown')
                                comments = preprocess_comments_dataframe(comments)
                                comments_df_list.append(comments)
                                if printout:
                                    print('Retrieved {} comments from the article with url: '.format(number_comments))
                                    print(article_url)
                            if error:
                                break
                    if error:
                        break
            except KeyboardInterrupt:
                if printout:
                    print('KeyboardInterrupt: Retrieval interrupted.')
                    print()
                break
            except ConnectionError:
                if printout:
                    print('ConnectionError: Retrieval interrupted.')
                    print()
                break
            except SystemExit:
                if printout:
                    print('SystemExit: Retrieval interrupted.')
                    print()
                break
            except HTTPError:
                HTTPErrorCount += 1
                if HTTPErrorCount < 5:
                    if printout:
                        print(sys.exc_info()[1])
                        print("Page {} is skipped. Retrival is continued from the next page.".format(page))
                        print()
                    pass
                else:
                    if printout:
                        print(sys.exc_info()[1])
                        print("Retrival is terminated due to repeated HTTP errors.")
                        print()
                    break
            except JSONDecodeError:
                if printout:
                    print('JSONDecodeError: Retrieval interrupted.')
                    print()
                break
            except:
                if printout:
                    print(sys.exc_info()[0], sys.exc_info()[1])
                    print("Page {} is skipped. Retrival is continued from the next page.".format(page))
                    print()
                pass
        else:
            if printout:
                print('Maximum limit of {} for the comments have reached. Terminating retrieval.'.format(max_comments))
                print()
            break
                            
    if comments_df_list: # Check that the list is not empty
        comments_df = pd.concat([df for df in comments_df_list])
        comments_df = preprocess_comments_dataframe(comments_df)
        articles_df = pd.DataFrame(articles_list)
        articles_df = preprocess_articles_dataframe(articles_df)
        
    if printout:
        if page_lower > page_upper:
            print("page_lower value is greater than the page_upper. No articles and comments are returned.")
        elif (begin_date is not None) & (end_date is not None):
            if begin_date > end_date:
                print("begin_date is bigger than the end_date. No articles and comments are returned.")
            else:
                print()
                print("Total articles stored: ", articles_df.shape[0])
                print("Total comments retrieved: ", comments_df.shape[0])
        else:
            print()
            print("Total articles stored: ", articles_df.shape[0])
            print("Total comments retrieved: ", comments_df.shape[0])
    if save:
        if filename:
            articles_df.to_csv('Articles' + filename + '.csv', index=False)
            comments_df.to_csv('Comments' + filename + '.csv', index=False)
        else:
            articles_df.to_csv('Articles.csv', index=False)
            comments_df.to_csv('Comments.csv', index=False)
    return articles_df, comments_df
 
    
def get_comments(article_url, printout=True, save=False, filename=None, internal=False):
    '''Given the url of an articles from NYT, returns a dataframe of comments in that article'''
    
    url = article_url.replace(':','%253A') #convert the : to an HTML entity
    url = url.replace('/','%252F')
    
    offset = 0 #Start off at the very beginning
    total_comments = 0 # Initialize the count of comments in the article 
    df_list = []
    comments_df = pd.DataFrame() # Set up a list to store the comments' data 
    error = None
    while True:
        try:
            sleep(1) 
            params = {'sort': "newest", 'offset': offset, 'url': article_url}
            
            # Get the comments data and convert it into json format
            file = requests.get(COMMENTS_URL, params=params).text.replace('NYTD.commentsInstance.drawComments(','').replace('      /**/ ','')[:-2] 
            js = json.loads(file) # Load the file as json
            if js['status'] == 'OK':
                results = js['results']
                total_comments_returned = results['totalCommentsReturned']
                if total_comments_returned:
                    comments = results['comments']
                    df = pd.DataFrame(comments)
                    df_list.append(df)
                else:
                    break # Break when no comments are returned
            offset = offset + 25 # Increment the counter since 25 comments are scraped each time
        except KeyboardInterrupt:
            if internal:
                error = True
            if printout:
                print('KeyboardInterrupt: Retrieval interrupted.')
                print()
            break
        except ConnectionError:
            if internal:
                error = True
            if printout:
                print('ConnectionError: Retrieval interrupted.')
                print()
            break
        except SystemExit:
            if internal:
                error = True
            if printout:
                print('SystemExit: Retrieval interrupted.')
                print()
            break
        except HTTPError:
            if printout:
                print(sys.exc_info()[1])
                print("Article with the URL {} is skipped. Retrival is continued from the next article.".format(article_url))
                print()
            break    
        except JSONDecodeError:
            if internal:
                error = True
            if printout:
                print('JSONDecodeError: Retrieval interrupted.')
                print()
            break
        except:
            if internal:
                error = True
            if printout:
                print(sys.exc_info()[0], sys.exc_info()[1])
            break
    if df_list:
        comments_df = pd.concat([df for df in df_list])
        comments_df.drop_duplicates(subset=['commentID'], inplace=True)
        comments_df['inReplyTo'] = None 
        comments_df = get_replies(comments_df)
    total_comments = comments_df.shape[0]   
    if save:
        if filename:
            comments_df.to_csv('Comments' + filename + '.csv', index=False)
        else:
            comments_df.to_csv('Comments.csv', index=False)
    if internal:
        return comments_df, error
    else:
        if printout:
            if total_comments:
                comments_df = preprocess_comments_dataframe(comments_df)
            print('Retrieved {} comments from the article with url: '.format(total_comments))
            print(article_url)
        return comments_df

def get_articles(ARTICLE_API_KEY, page_lower=0, page_upper=50, begin_date=None, end_date=None, 
                 max_articles=100000, sort='newest', query=None, filter_query=None, printout=True, 
                save=False, filename=None):
    '''Collects the data on the articles of NYT using NYT articles search API, processes the 
    articles' data and returns a pandas dataframe for articles.'''
    
    params = {'api-key': ARTICLE_API_KEY}
    
    if page_lower<0:
        page_lower = 0
        if printout:
            print('Out of range value passed for page_lower. The page_lower parameter is set to 0.')
            print()
    
    if page_upper>200:
        page_upper = 200
        if printout:
            print('Out of range value passed for page_upper. The page_upper parameter is set to 199.')
            print()
        
    if (sort!='newest') & (sort!='oldest'):
        if printout:
            print('Invalid value passed for sort. The sort parameter is set to newest.')
            print()
    
    if sort=='oldest':
        if begin_date is None:
            begin_date = '20081031'   
    elif end_date is None:
        end_date = datetime.today().strftime('%Y%m%d')
    
    articles_df = pd.DataFrame()
    
    if begin_date: # Check begin_date is not None
        try:
            begin_date = pd.to_datetime(begin_date, errors='coerce').strftime('%Y%m%d')
        except:
            print("Error: Please try again with begin_date entered in the format %Y%m%d.")
            return articles_df
        params['begin_date'] = begin_date 

    if end_date: # Check end_date is not None
        try:
            end_date = pd.to_datetime(end_date, errors='coerce').strftime('%Y%m%d')
        except:
            print("Error: Please try again with end_date entered in the format %Y%m%d.")
            return articles_df
        params['end_date'] = end_date

    if query:
        params['q'] = query

    if filter_query:
        params['fq'] = filter_query
        
    params['sort'] = sort
    
    articles_list = []
    
    total_articles = 0
    
    HTTPErrorCount = 0
    
    for page in range(page_lower, page_upper):
        if total_articles < max_articles:
            sleep(1)
            
            params['page'] = page # Every page has 10 articles
            
            if printout:
                print("Page: ", page)
            try:
                # Using NYT API to get articles search data in json format
                js = requests.get(NYT_ARTICLE_API_URL, params=params).json()
                
                # First check whether API rate limit has exceeded
                if js.get('message'):
                    if printout:
                        print('NYT' + js.get('message') + 'for today. No more comments can be retrieved using the article search today, however the function get_comments can be used to retrieve further comments w/o limit if the URLs of the articles are given to the function manually.')
                    break
                
                # Check status to make sure data is retrieved correctly
                if js.get('status') == 'OK':
                    docs = js['response']['docs']
                    docs_length = len(docs)
                    if docs_length==0:
                        if printout:
                            print("No articles found on page", page)
                        break
                    for i in range(docs_length):
                        article = docs[i]
                        articles_list.append(article)
                        if printout:
                            article_url = article['web_url'] # Get the url for the article
                            print("Article url:", article_url)
            except KeyboardInterrupt:
                if printout:
                    print('KeyboardInterrupt: Retrieval interrupted.')
                break
            
            except ConnectionError:
                if printout:
                    print('ConnectionError: Retrieval interrupted.')
                break
            except SystemExit:
                if printout:
                    print('SystemExit: Retrieval interrupted.')
                break
            except HTTPError:
                HTTPErrorCount += 1
                if HTTPErrorCount < 5:
                    if printout:
                        print(sys.exc_info()[1], ". Page {} is skipped. Retrival is continued from the next page.".format(page))
                        print()
                    pass
                else:
                    if printout:
                        print(sys.exc_info()[1], ". Retrival is terminated due to repeated HTTP errors.")
                        print()
                    break
            except:
                if printout:
                    print(sys.exc_info()[0], sys.exc_info()[1])
                    print("Page {} is skipped. Retrival is continued from the next page.".format(page))
                    print()
                pass
        else:
            if printout:
                print('Maximum limit of {} for the comments have reached. Terminating retrieval.'.format(max_comments))
            break
    articles_df = pd.DataFrame(articles_list)
    articles_df = preprocess_articles_dataframe(articles_df)
        
    if printout:
        if page_lower > page_upper:
            print("page_lower value is greater than the page_upper. No articles returned.")
        elif (begin_date is not None) & (end_date is not None):
            if begin_date > end_date:
                print("begin_date is bigger than the end_date. No articles returned.")
            else:
                print()
                print("Total articles stored: ", articles_df.shape[0])
        else:
            print()
            print("Total articles stored: ", articles_df.shape[0])
    if save:
        if filename:
            articles_df.to_csv('Articles' + filename + '.csv', index=False)
        else:
            articles_df.to_csv('Articles.csv', index=False)
    return articles_df

