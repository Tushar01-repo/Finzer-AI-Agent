from pathlib import Path
import pathspec
import seedir as sd

def seedir_with_gitignore(repo_path):
    repo = Path(repo_path).resolve()
    gitignore_path = repo / '.gitignore'
    
    # 1. Parse .gitignore if it exists
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            spec = pathspec.PathSpec.from_lines('gitwildmatch', f.read().splitlines())
    else:
        spec = None

    # Containers for items to exclude
    exclude_folders = {'.git'}  # Always hide the system .git folder
    exclude_files = set()

    # 2. Walk the directory manually to find what matches .gitignore
    for path_obj in repo.rglob('*'):
        try:
            relative_path = path_obj.relative_to(repo)
        except ValueError:
            continue
            
        # If gitignore matches this file/folder, add its name to the exclusion sets
        if spec and spec.match_file(str(relative_path)):
            if path_obj.is_dir():
                exclude_folders.add(path_obj.name)
            else:
                exclude_files.add(path_obj.name)

    # 3. Print the tree using the natively supported kwargs
    sd.seedir(
        str(repo), 
        style='lines', 
        exclude_folders=list(exclude_folders), 
        exclude_files=list(exclude_files)
    )

if __name__ == '__main__':
    seedir_with_gitignore(r"C:\Users\paltu\Finzer-AI-Agent")


app/
├── main.py
│
├── api/
│
├── config/
│   ├── feeds.yaml
│   ├── feed_registry.py
│   └── settings.py
│
├── models/
│   ├── database_schema.py
│   ├── schema.sql
│   └── discovered_article.py       🆕
│
├── providers/
│   └── news/
│       ├── base.py                 🆕
│       ├── newsdata.py             🆕
│       └── registry.py             🆕
│
├── services/
│   ├── news_discovery_service.py   🆕
│   ├── article_content_extractor.py
│   ├── article_normalizer.py
│   ├── feed_sync_service.py
│   └── ingestion_service.py
│
├── extractors/
│   ├── base.py                     🆕
│   ├── bs4_extractor.py            🆕
│   └── playwright_extractor.py     🆕
│
├── repositories/
│   ├── article_feed_repository.py
│   ├── article_repository.py
│   ├── database.py
│   └── feed_repository.py
│
└── queue/
    ├── queue_publisher.py
    └── queue_topology.py