import os
import glob
import re

STATIC_DIR = "/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway/static"

NEW_SIDEBAR = """                <ul class="nav-list">
                    <li class="nav-item"><a href="/staff/service-stt"><i class="fa-solid fa-microphone-lines" style="width: 16px; text-align: center;"></i> Speech to Text</a></li>
                    <li class="nav-item"><a href="/staff/service-tts"><i class="fa-solid fa-volume-high" style="width: 16px; text-align: center;"></i> Text to Speech</a></li>
                    <li class="nav-item"><a href="/staff/service-llm"><i class="fa-solid fa-comments" style="width: 16px; text-align: center;"></i> LLM Chatbot</a></li>
                    <li class="nav-item"><a href="/staff/service-image"><i class="fa-solid fa-image" style="width: 16px; text-align: center;"></i> Image Gen API</a></li>
                    <li class="nav-item"><a href="/staff/service-moderation"><i class="fa-solid fa-shield-halved" style="width: 16px; text-align: center;"></i> Moderation API</a></li>
                </ul>"""

OLD_SIDEBAR_REGEX = re.compile(
    r'<ul class="nav-list">\s*<li class="nav-item"><a href="/staff/service\?name=Speech%20to%20Text">.*?</ul>',
    re.DOTALL
)

def fix_html_files():
    html_files = glob.glob(os.path.join(STATIC_DIR, "staff_*.html"))
    for file in html_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        if OLD_SIDEBAR_REGEX.search(content):
            content = OLD_SIDEBAR_REGEX.sub(NEW_SIDEBAR, content)
            
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed sidebar in {file}")

def fix_staff_apis_cards():
    apis_path = os.path.join(STATIC_DIR, "staff_apis.html")
    with open(apis_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "Image Generation API" not in content and "<!-- Image Generation Card -->" not in content:
        # Add the two cards inside api-cards-grid-container
        cards_addition = """
                <!-- Image Generation Card -->
                <div class="api-card" onclick="navigateToService('Image Generation API')">
                    <div class="card-top">
                        <div class="api-icon" style="background:#8b5cf6;"><i class="fa-solid fa-image"></i></div>
                        <label class="switch" onclick="event.stopPropagation()">
                            <input type="checkbox" id="toggle-image" onchange="handleApiToggleClick('Image Generation API', this, event)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="card-title">Image Generation API</div>
                    <div class="card-desc">Generate images from text using Stable Diffusion XL</div>
                </div>

                <!-- Content Moderation Card -->
                <div class="api-card" onclick="navigateToService('Content Moderation API')">
                    <div class="card-top">
                        <div class="api-icon" style="background:#ef4444;"><i class="fa-solid fa-shield-halved"></i></div>
                        <label class="switch" onclick="event.stopPropagation()">
                            <input type="checkbox" id="toggle-moderation" onchange="handleApiToggleClick('Content Moderation API', this, event)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="card-title">Content Moderation API</div>
                    <div class="card-desc">Scan and filter bad language / toxic text content</div>
                </div>
            </div>"""
        # Find the end of the grid container (</div> matching api-grid)
        # We will replace the last </div> before MODAL 1
        content = content.replace("</div>\n        </div>\n    </div>\n\n    <!-- MODAL 1:", cards_addition + "\n        </div>\n    </div>\n\n    <!-- MODAL 1:")
        
        with open(apis_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed staff_apis.html cards")

def fix_staff_layout_js():
    js_path = os.path.join(STATIC_DIR, "js", "staff_layout.js")
    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_fallback = """    return cached ? JSON.parse(cached) : [
        { name: "Speech to Text", unit: "block", free_quota: "10,000 blocks" },
        { name: "Text to Speech", unit: "character", free_quota: "100,000 characters" },
        { name: "LLM Chatbot API", unit: "token", free_quota: "50,000 tokens" }
    ];"""

    new_fallback = """    return cached ? JSON.parse(cached) : [
        { name: "Speech to Text", unit: "block", free_quota: "10,000 blocks" },
        { name: "Text to Speech", unit: "character", free_quota: "100,000 characters" },
        { name: "LLM Chatbot API", unit: "token", free_quota: "50,000 tokens" },
        { name: "Image Generation API", unit: "image", free_quota: "100 images" },
        { name: "Content Moderation API", unit: "request", free_quota: "10,000 requests" }
    ];"""

    if old_fallback in content:
        content = content.replace(old_fallback, new_fallback)
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed staff_layout.js fallback")

if __name__ == "__main__":
    fix_html_files()
    fix_staff_apis_cards()
    fix_staff_layout_js()
