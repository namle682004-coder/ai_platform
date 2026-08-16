import os
import glob
import re

STATIC_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway/static"

def fix_duplicate_declarations():
    html_files = glob.glob(os.path.join(STATIC_DIR, "staff_service_*.html"))
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find all occurrences of "let currentSnippetLang = 'curl';"
        count = content.count("let currentSnippetLang = 'curl';")
        if count > 1:
            # Replace the second occurrence onwards
            # Split by the string, then join the first piece with "let...", and the rest with just "" or comment it out
            parts = content.split("let currentSnippetLang = 'curl';")
            # We want to keep the first one
            new_content = parts[0] + "let currentSnippetLang = 'curl';" + "/* duplicate removed */".join(parts[1:])
            
            with open(file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Fixed duplicate declaration in {file}")

if __name__ == "__main__":
    fix_duplicate_declarations()
