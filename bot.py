import os
import time
import random
import urllib.parse
import xml.etree.ElementTree as ET
from io import BytesIO
import requests
from bs4 import BeautifulSoup
from google import genai
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from playwright.sync_api import sync_playwright

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NAVER_ID = os.environ.get("NAVER_ID", "").strip()
NAVER_PW = os.environ.get("NAVER_PW", "").strip()
INPUT_KEYWORD = os.environ.get("TARGET_KEYWORD", "자동").strip()

INFO_TOPICS = [
    "ISA 계좌 절세 혜택 및 ETF 투자 활용법",
    "미국 월배당 ETF 슈드(SCHD) 및 커버드콜 구조 비교",
    "연금저축펀드 세액공제 한도와 ETF 포트폴리오 구성법",
    "금리 변동기에 유리한 채권 ETF 듀레이션 투자 원리",
    "반도체 HBM 및 CXL 차세대 패키징 밸류체인 핵심 정리",
    "AI 데이터센터 전력설비 및 변압기 산업 수혜 구조",
    "기업 밸류업 프로그램 핵심 지표 PBR ROE 해석법",
    "환율 상승기 수혜 업종과 달러 ETF 투자 체크포인트"
]

def select_topic_and_fetch_news(user_keyword):
    headers = {"User-Agent": "Mozilla/5.0"}
    if user_keyword and user_keyword != "자동":
        return "지정주제", user_keyword, fetch_news_data(user_keyword)

    # 1순위: 최근 1시간 이내 실시간 속보 탐색
    breaking_query = urllib.parse.quote("속보 특징주 OR 공시 OR 급등")
    naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={breaking_query}&sort=1"
    try:
        res = requests.get(naver_url, headers=headers, timeout=7)
        soup = BeautifulSoup(res.text, 'html.parser')
        fresh_news = []
        for item in soup.select('.news_wrap')[:6]:
            time_info = item.select_one('.info_group span.info')
            title_el = item.select_one('.news_tit')
            dsc_el = item.select_one('.dsc_txt')
            if time_info and title_el:
                t_text = time_info.get_text(strip=True)
                if "분 전" in t_text:
                    fresh_news.append(f"[{t_text} 속보] {title_el.get_text(strip=True)} - {dsc_el.get_text(strip=True) if dsc_el else ''}")
        if len(fresh_news) >= 2:
            return "실시간속보", "실시간 시장 속보 및 특징주", "\n".join(fresh_news)
    except Exception:
        pass

    # 2순위: 속보 없을 시 정보 5 : 종목 5 랜덤 선택
    mode = random.choice(["정보성", "종목분석"])
    if mode == "종목분석":
        try:
            fin_res = requests.get("https://finance.naver.com/sise/lastsearch2.naver", headers=headers, timeout=7)
            fin_soup = BeautifulSoup(fin_res.content.decode('euc-kr', 'replace'), 'html.parser')
            stocks = [a.get_text(strip=True) for a in fin_soup.select('a.tltle')[:10]]
            if stocks:
                chosen_stock = random.choice(stocks)
                return "종목분석", chosen_stock, fetch_news_data(chosen_stock)
        except Exception:
            pass
        chosen_stock = random.choice(["SK하이닉스", "삼성전자", "현대차", "한국전력", "알테오젠", "HD현대일렉트릭"])
        return "종목분석", chosen_stock, fetch_news_data(chosen_stock)
    else:
        chosen_info = random.choice(INFO_TOPICS)
        return "정보성", chosen_info, fetch_news_data(chosen_info)

def fetch_news_data(keyword):
    encoded = urllib.parse.quote(keyword)
    articles = []
    try:
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=7)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:6]:
            articles.append(f"보도: {item.find('title').text}")
    except Exception:
        pass
    try:
        naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={encoded}&sort=1"
        page = requests.get(naver_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
        soup = BeautifulSoup(page.text, 'html.parser')
        for dsc in soup.select('.api_txt_lines.dsc_txt')[:5]:
            articles.append(f"요약: {dsc.get_text(strip=True)}")
    except Exception:
        pass
    return "\n".join(articles) if articles else f"{keyword} 관련 최신 시장 동향"

def write_blog(category, keyword, news_text):
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
현재 작성 모드: [{category}]
주제/키워드: {keyword}
참고할 실시간 뉴스/시장 데이터 (언론사명이나 출처는 절대 본문에 적지 말 것):
{news_text}

----------------------------------------------
위 주제와 데이터를 바탕으로 네이버 블로그 포스팅을 작성해줘.
만약 현재 작성 모드가 [실시간속보]라면, 수집된 속보들 중 가장 시장 파급력이 큰 핵심 이슈나 특징주 1개를 중심으로 글을 풀어줘.

[유연한 작성 지침]
글의 주제(속보 브리핑 vs 개별 종목 분석 vs 재테크·ETF 정보)에 맞춰 가장 자연스럽고 읽기 편하게 유도리 있게 변형해서 작성해줘.
1. 도입부: 첫 문단은 핵심 훅으로 시작, 둘째 문단은 왜 중요한지 설명, 셋째 문단은 “먼저 결론부터 말씀드리면,”으로 시작해 핵심을 바로 짚어줄 것.
2. 문체: 짧은 문장 위주로 리듬감 있게 쓰고, 한 문단은 1~3문장으로 짧게 끊을 것. '니다' 50%, '요' 50% 비율을 자연스럽게 섞어 쓸 것. (쉽게 말하면, 결국 여기서 중요한 건, 개인적으로는 등의 표현 활용)
3. 서식:
   - 소제목은 # 이모지+숫자. 소제목 형식으로 작성 (예: # 🔥1. 시장이 주목하는 이유)
   - 섹션 사이, 면책사항 앞, 해시태그 앞에는 단독 한 줄로 --- 구분선 삽입
   - 문단 내 번호는 ❶, ❷, ❸ 기호 사용
   - 인용구(> 활용)와 2~3열짜리 Markdown 표를 본문에 자연스럽게 포함
   - 본문에 ** 강조기호, HTML 태그, 출처, 언론사명, 물결표(~) 절대 사용 금지 (숫자 범위는 'A에서 B까지'로 표기)
4. 마무리:
   - 투자/종목 글이면 후반부에 핵심 Q&A 3~5가지를 넣고 마지막 문장은 “투자 판단과 책임은 본인에게 있습니다.”로 끝낼 것.
   - 정보성 글이면 Q&A 없이 깔끔한 정리 문장으로 마무리할 것.
   - 맨 아래에 #서이추 포함 해시태그 25~30개를 가로로 나열할 것.

[출력 규격]
첫째 줄: [제목] 핵심 키워드가 들어간 짧고 강렬한 검색용 제목
둘째 줄: [썸네일] 이 글 전체를 대표하는 단 하나의 핵심 종목명 또는 키워드 (부연설명 없이 8자 이내 단어만!)
셋째 줄: [배경묘사] 이 글의 주제와 분위기를 상징하는 고화질 3D 디지털 아트 일러스트 배경 생성용 영어 프롬프트 (글자 없음, 15단어 이내)
넷째 줄부터: 아무런 안내 문구 없이 바로 본문 첫 문단 시작
"""
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    return res.text

def make_free_ai_thumbnail(thumb_word, bg_prompt):
    """완성된 본문 맞춤형 무료 AI 3D 일러스트 배경(1000x1000) + 선명한 종목명 타이포그래피 합성"""
    img = None
    try:
        full_prompt = f"{bg_prompt}, modern 3d financial digital art, cinematic lighting, dark moody atmosphere, high resolution, strictly no text, no letters"
        encoded_bg = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 99999)
        bg_url = f"https://image.pollinations.ai/prompt/{encoded_bg}?width=1000&height=1000&nologo=true&seed={seed}&model=flux"
        r = requests.get(bg_url, timeout=12)
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB").resize((1000, 1000))
            # 글자가 눈에 확 들어오도록 배경 명도를 살짝 낮춤
            img = ImageEnhance.Brightness(img).enhance(0.45)
    except Exception:
        pass

    # 만약 무료 AI 이미지 서버가 응답이 늦을 경우 즉시 세련된 다크 그라데이션 배경 생성
    if img is None:
        img = Image.new('RGB', (1000, 1000))
        draw_bg = ImageDraw.Draw(img)
        for y in range(1000):
            draw_bg.line([(0, y), (1000, y)], fill=(int(15 + y*0.02), int(22 + y*0.03), int(42 + y*0.05)))

    draw = ImageDraw.Draw(img)
    # 고급스러운 테두리 프레임 추가
    draw.rectangle([40, 40, 960, 960], outline=(100, 185, 255), width=6)
    draw.rectangle([58, 58, 942, 942], outline=(255, 255, 255), width=2)

    font_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    length = len(thumb_word)
    font_size = 155 if length <= 4 else (125 if length <= 6 else (95 if length <= 9 else 75))
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), thumb_word, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        w, h = len(thumb_word) * font_size * 0.85, font_size

    x, y = (1000 - w) // 2, (1000 - h) // 2 - 15
    # 진한 외곽선 그림자 처리로 가독성 극대화
    for dx, dy in [(-6, -6), (6, -6), (-6, 6), (6, 6), (0, 8)]:
        draw.text((x + dx, y + dy), thumb_word, font=font, fill=(0, 0, 0))
    draw.text((x, y), thumb_word, font=font, fill=(255, 255, 255))
    
    abs_path = os.path.abspath("thumb.png")
    img.save(abs_path)
    return abs_path

def send_post_to_telegram(category, thumb_word, title, body):
    """완성된 [맨 위 썸네일 + 아래 본문]을 텔레그램으로도 즉시 전송"""
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    caption_text = f"🏷️ 분류: [{category}] ({thumb_word})\n📌 제목:\n{title}"
    
    with open("thumb.png", "rb") as f:
        requests.post(photo_url, data={"chat_id": TG_CHAT_ID, "caption": caption_text}, files={"photo": f}, timeout=15)
        
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    max_len = 3800
    if len(body) <= max_len:
        requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": body}, timeout=15)
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
            requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": part.strip()}, timeout=15)

def save_to_naver_blog_with_image(title, body, thumb_abs_path):
    """네이버 스마트에디터 ONE 접속 -> 제목 입력 -> 맨 위에 썸네일 사진 첨부 -> 그 아래 본문 입력 -> 임시저장"""
    if not NAVER_ID or not NAVER_PW:
        return "ℹ️ 네이버 ID/PW 미입력 상태 (텔레그램으로 썸네일+본문 전송 완료)"
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        
        try:
            page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            time.sleep(2)
            page.evaluate(f"document.getElementById('id').value = '{NAVER_ID}';")
            page.evaluate(f"document.getElementById('pw').value = '{NAVER_PW}';")
            time.sleep(1)
            page.click("#log\\.login")
            time.sleep(5)
            
            if "nidlogin" in page.url:
                page.screenshot(path="status.png")
                browser.close()
                return "⚠️ 네이버 로그인 차단됨 (네이버 보안설정에서 '타지역 로그인 차단'을 해제해 주세요)"
                
            page.goto(f"https://blog.naver.com/{NAVER_ID}?Redirect=Write&", wait_until="domcontentloaded")
            time.sleep(5)
            
            frame = page.frame(name="mainFrame")
            if not frame:
                page.screenshot(path="status.png")
                browser.close()
                return "❌ 스마트에디터 화면 진입 실패"
                
            # 팝업창 닫기
            for selector in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
                try:
                    if frame.locator(selector).is_visible(timeout=2000):
                        frame.locator(selector).click()
                        time.sleep(0.5)
                except Exception:
                    pass
                    
            # 1. 제목 입력
            frame.locator(".se-documentTitle .se-text-paragraph").click()
            time.sleep(0.5)
            page.keyboard.insert_text(title)
            
            # 2. 본문 영역 첫 줄 클릭 후 맨 위에 1000x1000 썸네일 이미지 업로드
            frame.locator(".se-component.se-text .se-text-paragraph").first.click()
            time.sleep(0.5)
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    frame.locator("button.se-image-toolbar-button, button[data-name='image']").first.click()
                file_chooser = fc_info.value
                file_chooser.set_files(thumb_abs_path)
                time.sleep(4) # 이미지 업로드 완료 대기
                page.keyboard.press("Enter")
                time.sleep(0.5)
            except Exception as img_e:
                print(f"이미지 업로드 버튼 우회: {img_e}", flush=True)
                
            # 3. 썸네일 바로 아래에 본문 글 전체 입력
            page.keyboard.insert_text(body)
            time.sleep(2)
            
            # 4. 임시저장 클릭
            frame.locator("button:has-text('저장'), .save_btn__bzc5B").first.click()
            time.sleep(3)
            
            page.screenshot(path="status.png")
            browser.close()
            return "✅ 네이버 블로그 [맨 위 썸네일 + 아래 본문] 자동 임시저장 완료!"
        except Exception as e:
            try: page.screenshot(path="status.png")
            except Exception: pass
            browser.close()
            return f"⚠️ 네이버 임시저장 건너뜀: {str(e)[:80]}"

if __name__ == "__main__":
    category, target_topic, news_data = select_topic_and_fetch_news(INPUT_KEYWORD)
    raw_post = write_blog(category, target_topic, news_data)
    
    title_txt = f"{target_topic} 핵심 정리"
    thumb_word = target_topic[:8]
    bg_prompt = "modern 3d stock market financial abstract illustration"
    body_lines = []
    
    for line in raw_post.strip().split('\n'):
        if line.startswith("[제목]"):
            title_txt = line.replace("[제목]", "").strip()
        elif line.startswith("[썸네일]"):
            thumb_word = line.replace("[썸네일]", "").strip()
        elif line.startswith("[배경묘사]"):
            bg_prompt = line.replace("[배경묘사]", "").strip()
        else:
            body_lines.append(line.replace("**", ""))
            
    final_body = "\n".join(body_lines).strip()
    
    # 1. 무료 AI로 본문 맞춤형 1000x1000 썸네일 생성
    thumb_path = make_free_ai_thumbnail(thumb_word, bg_prompt)
    
    # 2. 텔레그램으로 [맨 위 썸네일 사진 + 그 아래 본문 글] 즉시 전송
    send_post_to_telegram(category, thumb_word, title_txt, final_body)
    
    # 3. 네이버 블로그 에디터에도 [맨 위 썸네일 + 그 아래 본문] 형태로 임시저장 시도
    status_msg = save_to_naver_blog_with_image(title_txt, final_body, thumb_path)
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": status_msg}, timeout=10)
    if os.path.exists("status.png"):
        photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        with open("status.png", "rb") as f:
            requests.post(photo_url, data={"chat_id": TG_CHAT_ID, "caption": "🖥️ 네이버 에디터 실행 화면"}, files={"photo": f}, timeout=15)
