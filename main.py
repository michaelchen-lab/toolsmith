from serpapi import GoogleSearch
import json, os, requests, re, unicodedata, base64
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from pydantic import BaseModel, Field
from tqdm import tqdm
from pypdf import PdfReader
from pypdf.errors import PdfReadError

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.getenv('OPENROUTER_API_KEY'),
)

GET_NEW_SEARCH_RESULTS=True
NO_OF_QUERIES=3
PAPERS_PER_QUERY=5
SAVE_PAPERS_LOCALLY=True

class Task(BaseModel):
    Name: str
    Description: str
    Databases: list[str]
    Specialized_Tools: list[str]
    Software_Packages: list[str]

class Tasks(BaseModel):
    tasks: list[Task]

class SearchQueries(BaseModel):
    queries: list[str]

class Tool(BaseModel):
    name: str
    type_of_tool: str
    function: str

class Tools(BaseModel):
    tools: list[Tool]

with open('./prompts/identify_tools_in_paper.txt', 'r') as file:
    IDENTIFY_TOOLS_FROM_PAPER_PROMPT = file.read()

with open('./prompts/generate_google_scholar_query.txt', 'r') as file:
    GENERATE_GOOGLE_SCHOLAR_QUERY_PROMPT = file.read()

with open('./prompts/select_tools.txt', 'r') as file:
    SELECT_TOOLS_PROMPT = file.read()

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

def extract_tools():
    with open('temp/sample_all_tasks2.json', 'r') as file:
        tasks_by_paper = json.load(file)
    all_tools = []
    for tasks in tasks_by_paper:
        for task in tasks['tasks']:
            tools = task['Databases']+task['Specialized_Tools']+task['Software_Packages']
            tool_types = ['database']*len(task['Databases'])+['specialized_tools']*len(task['Specialized_Tools'])+['software']*len(task['Software_Packages'])
            for tool, tool_type in zip(tools, tool_types):
                all_tools.append({
                    'tool_name': tool, 'type_of_tool': tool_type,
                    'function': task['Name'] + '\n\n' + task['Description']
                })
                # print(tool, '-', tool_type)

    completion = client.chat.completions.parse(
        model="google/gemini-2.0-flash-lite-001",
        messages=[{
            "role": "user",
            "content": [{
                "type": "text",
                "text": SELECT_TOOLS_PROMPT.format(user_query, json.dumps(all_tools, indent=4))
            }]
        }],
        response_format=Tools
    )
    essential_tools = json.loads(completion.choices[0].message.content)
    print(json.dumps(essential_tools,indent=4))
    with open('temp/sample_essential_tools.json', 'w') as file:
        json.dump(essential_tools, file, indent=4)

def check_pdf_content(file_path: str) -> bool:
    """
    Checks if a PDF file is valid, non-empty (0-bytes), 
    and contains at least one page.
    """
    try:
        # Check for 0-byte file first
        if os.path.getsize(file_path) == 0:
            return False
            
        reader = PdfReader(file_path)
        
        # Return True if page count is greater than 0
        return len(reader.pages) > 0
        
    except (PdfReadError, Exception):
        # Catches 0-byte errors, corrupt files, or other read errors
        return False

def main(user_query):
    # Step 1: LLM generate search query for Google Scholar
    completion = client.chat.completions.parse(
        model="google/gemini-2.0-flash-lite-001",
        messages=[{
            "role": "user",
            "content": [{
                "type": "text",
                "text": GENERATE_GOOGLE_SCHOLAR_QUERY_PROMPT.format(user_query)
            }]
        }],
        response_format=SearchQueries
    )
    search_queries = json.loads(completion.choices[0].message.content)
    print('GOOGLE SCHOLAR QUERY:')
    for i in range(NO_OF_QUERIES): print(' - {}'.format(search_queries['queries'][i]))
    print()

    # Step 2: Extract the list of relevant papers
    if GET_NEW_SEARCH_RESULTS:
        results = []
        for i in tqdm(range(NO_OF_QUERIES), desc='Extracting papers from Google Scholar'):
            params = {
                "api_key": os.getenv('SERPAPI_KEY'),
                "engine": "google_scholar",
                "q": search_queries['queries'][i],
                "num": PAPERS_PER_QUERY,
                "hl": "en"
            }
            search = GoogleSearch(params)
            results += search.get_dict()['organic_results']
        
        with open('output/1_google_scholar_search_results.json', 'w') as file:
            json.dump(results, file, indent=4)
    else:
        with open('temp/sample_serpapi_results.json', 'r') as file:
            results = json.load(file)
    
    ## Parse API output
    papers = []
    for r in tqdm(results, desc='Parsing and downloading papers'):
        try:
            paper = {
                'id': r['result_id'],
                'title': r['title'],
                'link': r['resources'][0]['link'],
                'filename': '{}_{}.pdf'.format(r['result_id'], slugify(r['title']))
            }

            if SAVE_PAPERS_LOCALLY and not os.path.isfile('./downloads/{}'.format(paper['filename'])):
                response = requests.get(r['resources'][0]['link'])
                with open('./downloads/{}'.format(paper['filename']), 'wb') as f:
                    f.write(response.content)
                
            if check_pdf_content('./downloads/{}'.format(paper['filename'])):
                # print('Passed pdf check:', paper['title'])
                papers.append(paper)

        except Exception as e:
            print('An error occured when parsing results for {}.\nThis could be because a PDF link is not available'
                .format(r['title']))
            print(e)
    print('PAPERS ({} total):'.format(len(papers)))
    for p in papers: print(' - {}'.format(p['title']))
    print()
    with open('output/2_parsed_papers.json', 'w') as file:
        json.dump(papers, file, indent=4)

    # Step 3: Read the papers to identify all tools used
    all_tasks = []
    for paper in tqdm(papers, desc='Extracting tools from papers'):
        try:
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
            all_tasks.append(json.loads(completion.choices[0].message.content))
        except Exception as e:
            print('Tools could not be extracted from paper ({})\n\n{}'.format(paper['title'], e))
    
    with open('output/3_tools_from_papers.json', 'w') as file:
        json.dump(all_tasks, file, indent=4)

    # Step 4: Narrow down tools to the ones relevant to the input
    print('Identifying and filtering for essential tools...')
    all_tools = []
    for tasks in all_tasks:
        for task in tasks['tasks']:
            tools = task['Databases']+task['Specialized_Tools']+task['Software_Packages']
            tool_types = ['database']*len(task['Databases'])+['specialized_tools']*len(task['Specialized_Tools'])+['software']*len(task['Software_Packages'])
            for tool, tool_type in zip(tools, tool_types):
                all_tools.append({
                    'tool_name': tool, 'type_of_tool': tool_type,
                    'function': task['Name'] + '\n\n' + task['Description']
                })
                # print(tool, '-', tool_type)

    completion = client.chat.completions.parse(
        model="google/gemini-2.0-flash-lite-001",
        messages=[{
            "role": "user",
            "content": [{
                "type": "text",
                "text": SELECT_TOOLS_PROMPT.format(user_query, json.dumps(all_tools, indent=4))
            }]
        }],
        response_format=Tools
    )
    essential_tools = json.loads(completion.choices[0].message.content)
    print(json.dumps(essential_tools,indent=4))
    print('SUCCESS! {} essential tools identified.'.format(len(essential_tools['tools'])))
    with open('output/4_essential_tools.json', 'w') as file:
        json.dump(essential_tools, file, indent=4)

if __name__ == "__main__":
    user_query = "Task: Gene regulatory network (GRN) analysis with pySCENIC + snATAC\nGoal: Map transcription factor (TF) circuits that drive skeletal development across anatomical regions and developmental stages."
    main(user_query)
    # print(check_pdf_content('downloads/q4oX0LU-i1wJ_integrative-single-cell-rna-seq-and-atac-seq-identifies-transcriptional-and-epigenetic-blueprint-guiding-osteoclastogenic-trajectory.pdf'))
    # print(check_pdf_content('downloads/6_FB5prrs88J_biomni-a-general-purpose-biomedical-ai-agent.pdf'))
