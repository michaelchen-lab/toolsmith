# Toolsmith

## Installation

```
git clone https://github.com/michaelchen-lab/toolsmith
cd toolsmith
uv sync
.venv\Scripts\activate
```

## How to Run

1. Create `.env` file with `OPENROUTER_API_KEY=<token>` and `SERPAPI_KEY=<token>`
2. `python main.py`
   - `--query`: User task.
   - `--num-queries`: Number of Google Scholar queries to run (Max: 3; Default: 3)
   - `--papers-per-query`: Number of papers to extract per query (Default: 5)
3. The output will be saved in `\output` as `4_essential_tools.json`

## Example

An example query derived from Biomni's experiments:

```
Task: Gene regulatory network (GRN) analysis with pySCENIC + snATAC
Goal: Map transcription factor (TF) circuits that drive skeletal development across anatomical regions and developmental stages.
```

Output files for each of the 4 stages can be found in `\output`.