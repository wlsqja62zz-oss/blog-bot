import os
import time
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from google import genai
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NAVER_ID = os.environ.get("NAVER_ID", "").strip()
NAVER_PW = os.environ.get("NAVER_PW", "").strip()
KEYWORD = os.environ.get("TARGET_KEYWORD", "속보 특징주")

def get_news_without_api(keyword):
    encoded = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    res = requests.get(url)
    root = ET.fromstring(res.text)
    
    articles = []
    for item in root.findall('.//item')[:7]:
        title = item.find('title').text
        pub_date = item.find('pubDate').text
        articles.append(f"최신 보도({pub_date}): {title}")
    
    naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={encoded}&sort=1"
    page = requests.get(naver_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(page.text, 'html.parser')
    for dsc in soup.select('.api_txt_lines.dsc_txt')[:5]:
        articles.append(f"상세 내용: {dsc.get_text(strip=True)}")
        
    return "\n".join(articles)

def write_blog(keyword, news_text):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
입력된 주제/키워드: {keyword}
참고할 최신 뉴스 데이터:
{news_text}

----------------------------------------------
위 주제와 뉴스 흐름을 바탕으로 네이버 블로그용 주식, ETF, 산업, 테마, 재테크 글을 작성해줘.
- 첫 문단은 핵심이 바로 보이는 훅으로 시작, 둘째 문단은 왜 중요한지 설명, 셋째 문단은 반드시 “먼저 결론부터 말씀드리면,”으로 시작할 것.
- 고정 목차형이 아닌 우선순위형 구조로 2,000자 내외로 작성할 것.
- 문체는 짧은 문장 위주로 '니다' 50%, '요' 50%를 섞고, 한 문단은 1~3문장으로 짧게 끊을 것.
- 섹션 구분선은 단독 한 줄로 --- 를 출력하고, 소제목은 # 이모지+숫자. 소제목 형식으로 작성할 것.
- 문단 앞 숫자는 ❶, ❷, ❸ 형태를 쓰고, 인용구(>)와 2~3열짜리 Markdown 표를 본문에 포함할 것.
- 출처, 언론사명, 링크, ** 강조기호는 절대 넣지 말 것.
- 후반부에 투자자 Q&A 5가지를 넣고, 마지막 문장은 “투자 판단과 책임은 본인에게 있습니다.”로 끝낸 뒤 아래에 #서이추 포함 해시태그 30개를 가로로 나열할 것.

[출력 규격 - 필수]
첫째 줄: [썸네일] 오직 단 하나의 핵심 종목명 또는 키워드만 출력
둘째 줄: [제목] 핵심 키워드가 포함된 짧고 강렬한 검색용 제목
셋째 줄부터: 제목이나 안내 문구 없이 바로 본문 첫 문단 시작
"""
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    return res.text

def make_thumbnail(text):
    img = Image.new('RGB', (1000, 1000), color=(18, 26, 48))
    draw = ImageDraw.Draw(img)
    draw.rectangle([45, 45, 955, 955], outline=(90, 165, 255), width=8)
    
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    font_size = 130 if len(text) <= 5 else (100 if len(text) <= 8 else 75)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except:
        w, h = len(text) * font_size * 0.8, font_size
        
    draw.text(((1000 - w) // 2, (1000 - h) // 2 - 20), text, font=font, fill=(255, 255, 255))
    img.save("thumb.png")

def save_to_naver_blog(title, body):
    """Playwright를 이용해 네이버 로그인 후 스마트에디터 ONE에 임시저장"""
    if not NAVER_ID or not NAVER_PW:
        return "⚠️ NAVER_ID 또는 NAVER_PW가 설정되지 않아 임시저장을 건너뛰었습니다."
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = context.new_page()
        
        try:
            # 1. 네이버 로그인 페이지 접속 및 캡차 우회 입력
            page.goto("https://nid.naver.com/nidlogin.login", wait_until="networkidle")
            time.sleep(2)
            
            # 자바스크립트로 값 주입 (자동입력 방지 캡차 우회율 상승)
            page.evaluate(f"document.getElementById('id').value = '{NAVER_ID}';")
            page.evaluate(f"document.getElementById('pw').value = '{NAVER_PW}';")
            time.sleep(1)
            page.click("#log\\.login")
            
            # 2단계 인증 대기 또는 로그인 처리 대기 (10초)
            time.sleep(10)
            
            # 로그인 실패(캡차/해외차단 등) 여부 확인
            if "nidlogin" in page.url:
                page.screenshot(path="status.png")
                browser.close()
                return "❌ 네이버 로그인 단계에서 보안 확인(캡차/해외차단/2단계인증)이 걸렸습니다. 첨부된 화면 캡처를 확인해 주세요."
                
            # 2. 블로그 글쓰기 화면 이동
            page.goto(f"https://blog.naver.com/{NAVER_ID}?Redirect=Write&", wait_until="networkidle")
            time.sleep(6)
            
            frame = page.frame(name="mainFrame")
            if not frame:
                page.screenshot(path="status.png")
                browser.close()
                return "❌ 블로그 에디터(mainFrame)를 불러오지 못했습니다."
                
            # 3. 팝업창(작성 중인 글 이어쓰기 취소, 도움말 닫기) 정리
            try:
                if frame.locator(".se-popup-button-cancel").is_visible(timeout=3000):
                    frame.locator(".se-popup-button-cancel").click()
                    time.sleep(1)
            except:
                pass
            try:
                if frame.locator(".se-help-panel-close-button").is_visible(timeout=3000):
                    frame.locator(".se-help-panel-close-button").click()
                    time.sleep(1)
            except:
                pass
                
            # 4. 제목 입력
            frame.locator(".se-documentTitle .se-text-paragraph").click()
            time.sleep(1)
            page.keyboard.insert_text(title)
            time.sleep(1)
            
            # 5. 본문 이동 및 원고 입력
            frame.locator(".se-component.se-text .se-text-paragraph").first.click()
            time.sleep(1)
            for line in body.split('\n'):
                page.keyboard.insert_text(line)
                page.keyboard.press("Enter")
                time.sleep(0.03)
                
            time.sleep(2)
            
            # 6. 임시저장 버튼 클릭
            save_btn = frame.locator("button:has-text('저장'), .save_btn__bzc5B").first
            save_btn.click()
            time.sleep(3)
            
            page.screenshot(path="status.png")
            browser.close()
            return "✅ 네이버 블로그 [임시저장]까지 완료되었습니다! 블로그 앱 임시보관함을 확인해 보세요."
            
        except Exception as e:
            try:
                page.screenshot(path="status.png")
            except:
                pass
            browser.close()
            return f"⚠️ 에디터 조작 중 오류 발생: {str(e)[:150]}"

def send_telegram(title, body, status_msg):
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    with open("thumb.png", "rb") as f:
        requests.post(
            photo_url,
            data={"chat_id": TG_CHAT_ID, "caption": f"📌 추천 제목:\n{title}\n\n{status_msg}"},
            files={"photo": f}
        )
        
    # 에디터 진행 화면(성공 또는 로그인 막힘 화면) 캡처 전송
    if os.path.exists("status.png"):
        with open("status.png", "rb") as f:
            requests.post(
                photo_url,
                data={"chat_id": TG_CHAT_ID, "caption": "🖥️ 클라우드 브라우저 실행 화면"},
                files={"photo": f}
            )
            
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    max_len = 3800
    if len(body) <= max_len:
        requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": body})
    else:
        parts, current = [], ""
        for line in body.split('\n'):
            if len(current) + len(line) + 1 > max_len:
                parts.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current: parts.append(current)
        for part in parts:
            requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": part.strip()})

if __name__ == "__main__":
    news = get_news_without_api(KEYWORD)
    if news:
        raw = write_blog(KEYWORD, news)
        thumb_txt, title_txt, body_lines = KEYWORD, f"{KEYWORD} 핵심 정리", []
        for line in raw.strip().split('\n'):
            if line.startswith("[썸네일]"): thumb_txt = line.replace("[썸네일]", "").strip()
            elif line.startswith("[제목]"): title_txt = line.replace("[제목]", "").strip()
            else: body_lines.append(line.replace("**", ""))
            
        final_body = "\n".join(body_lines).strip()
        make_thumbnail(thumb_txt)
        status = save_to_naver_blog(title_txt, final_body)
        send_telegram(title_txt, final_body, status)
