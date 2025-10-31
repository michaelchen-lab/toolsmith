from serpapi import GoogleSearch
import json, os, requests, re, unicodedata, base64
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from pydantic import BaseModel, Field

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv('OPENROUTER_API_KEY'),
)

GET_NEW_SEARCH_RESULTS=False
NO_OF_PAPERS=10
SAVE_PAPERS_LOCALLY=True

class Task(BaseModel):
    Name: str
    Description: str
    Databases: list[str]
    Specialized_Tools: list[str]
    Software_Packages: list[str]

class Tasks(BaseModel):
    tasks: list[Task]

with open('./prompts/identify_tools_in_paper.txt', 'r') as file:
    IDENTIFY_TOOLS_FROM_PAPER_PROMPT = file.read()

def slugify(value, allow_unicode=False):
    """Convert string to filename friendly string"""
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def encode_pdf_to_base64(pdf_path):
    with open(pdf_path, "rb") as pdf_file:
        return base64.b64encode(pdf_file.read()).decode('utf-8')

def main(input):
    # Step 1: LLM generate search query for Google Scholar

    # Step 2: Extract the list of relevant papers
    query = "multi-token prediction for language models"
    if GET_NEW_SEARCH_RESULTS:
        params = {
            "api_key": os.getenv('SERPAPI_KEY'),
            "engine": "google_scholar",
            "q": query,
            "num": NO_OF_PAPERS,
            "hl": "en"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
    else:
        with open('temp/sample_serpapi_results.json', 'r') as file:
            results = json.load(file)
    
    ## Parse API output
    papers = []
    for r in results['organic_results']:
        try:
            paper = {
                'id': r['result_id'],
                'title': r['title'],
                'link': r['resources'][0]['link'],
                'filename': '{}_{}.pdf'.format(r['result_id'], slugify(r['title']))
            }
            papers.append(paper)

            if SAVE_PAPERS_LOCALLY and not os.path.isfile('./downloads/{}'.format(paper['filename'])):
                response = requests.get(r['resources'][0]['link'])
                with open('./downloads/{}'.format(paper['filename']), 'wb') as f:
                    f.write(response.content)
        except:
            print('An error occured when parsing results for {}.\nThis could be because a PDF link is not available'
                .format(r['title']))
            pass

    # Step 3: Read the papers to identify all tools used
    for paper in papers[:1]:
        base64_pdf = encode_pdf_to_base64('./downloads/{}'.format(paper['filename']))
        data_url = f"data:application/pdf;base64,{base64_pdf}"

        completion = client.chat.completions.parse(
            model="google/gemini-2.0-flash-lite-001",
            messages=[{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": IDENTIFY_TOOLS_FROM_PAPER_PROMPT
                }, {
                    "type": "file",
                    "file": {
                        "filename": "paper.pdf", "file_data": data_url
                    }
                },]
            }],
            response_format=Tasks
        )
        tasks = completion.choices[0].message.content

    # Step 4: Narrow down tools to the ones relevant to the input


if __name__ == "__main__":
    main(input)
