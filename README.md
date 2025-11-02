# Toolsmith

## How to Run

1. Create .env file with OPENROUTER_API_KEY=<token> and SERPAPI_KEY=<token>
2. `python main.py`
   - `--query`: User task.
   - `--num-queries`: Number of Google Scholar queries to run (Max: 3; Default: 3)
   - `--papers-per-query`: Number of papers to extract per query (Default: 5)
