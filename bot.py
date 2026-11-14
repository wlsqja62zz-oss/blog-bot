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

# 속보가 없을 때 50% 확률로 사용할 '알짜 재테크/ETF/산업 정보' 주제 풀
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
    """
    1. 사용자가 직접 키워드를 입력했으면 해당 키워드로 검색
    2. '자동'이면 실시간 속보(1분~1시간 내) 먼저 탐색
    3. 속보가 없으면 [정보 5 : 종목 5] 비율로 주제 자동 선정
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # (A) 사용자가 특정 키워드를 지정한 경우
    if user_keyword and user_keyword != "자동":
        return "지정주제", user_keyword, fetch_news_data(user_keyword)

    # (B) 1순위: 실시간 경제/증시 속보 탐색 (최근 1시간 이내 기사만 인정)
    breaking_query = urllib.parse.quote("속보 특징주 OR 공시 OR 급등")
    naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={breaking_query}&sort=1"
    try:
        res = requests.get(naver_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        news_items = soup.select('.news_wrap')
        
        fresh_news = []
        for item in news_items[:6]:
            time_info = item.select_one('.info_group span.info')
            title_el = item.select_one('.news_tit')
            dsc_el = item.select_one('.dsc_txt')
            if time_info and title_el:
                t_text = time_info.get_text(strip=True)
                # '분 전'이 포함된 실시간 속보만 추출
                if "분 전" in t_text:
                    fresh_news.append(f"[{t_text} 속보] {title_el.get_text(strip=True)} - {dsc_el.get_text(strip=True) if dsc_el else ''}")
        
        if len(fresh_news) >= 2:
            return "실시간속보", "실시간 시장 속보 및 특징주", "\n".join(fresh_news)
    except Exception:
        pass

    # (C) 2순위: 속보가 잠잠할 때 -> [정보 5 : 종목 5] 비율로 랜덤 선택
    mode = random.choice(["정보성", "종목분석"])
    
    if mode == "종목분석":
        # 네이버 금융 실시간 인기 검색 상위 종목 크롤링
        try:
            fin_res = requests.get("https://finance.naver.com/sise/lastsearch2.naver", headers=headers, timeout=10)
            fin_soup = BeautifulSoup(fin_res.content.decode('euc-kr', 'replace'), 'html.parser')
            stocks = [a.get_text(strip=True) for a in fin_soup.select('a.tltle')[:10]]
            if stocks:
                chosen_stock = random.choice(stocks)
                return "종목분석", chosen_stock, fetch_news_data(chosen_stock)
        except Exception:
            pass
        # 크롤링 실패 시 대표 관심 종목 중 선택
        chosen_stock = random.choice(["SK하이닉스", "삼성전자", "현대차", "한국전력", "알테오젠", "HD현대일렉트릭"])
        return "종목분석", chosen_stock, fetch_news_data(chosen_stock)
    else:
        chosen_info = random.choice(INFO_TOPICS)
        return "정보성", chosen_info, fetch_news_data(chosen_info)

def fetch_news_data(keyword):
    """키워드 관련 최신 뉴스 헤드라인과 요약문 수집"""
    encoded = urllib.parse.quote(keyword)
    articles = []
    
    try:
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=10)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:6]:
            articles.append(f"보도: {item.find('title').text}")
    except Exception:
        pass
        
    try:
        naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={encoded}&sort=1"
        page = requests.get(naver_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(page.text, 'html.parser')
        for dsc in soup.select('.api_txt_lines.dsc_txt')[:5]:
            articles.append(f"요약: {dsc.get_text(strip=True)}")
    except Exception:
        pass
        
    return "\n".join(articles) if articles else f"{keyword} 관련 최신 시장 동향 및 핵심 개념"

def write_blog(category, keyword, news_text):
    """1단계: 프롬프트를 유연하게 참조하여 본문 먼저 완성"""
    client = genai.Client(api_key=GEMINI_KEY)
    prompt = f"""
현재 작성 모드: [{category}]
주제/키워드: {keyword}
참고할 실시간 뉴스/시장 데이터 (언론사명이나 출처는 절대 본문에 적지 말 것):
{news_text}

----------------------------------------------
위 주제와 데이터를 바탕으로 네이버 블로그 포스팅을 작성해줘.
만약 현재 작성 모드가 [실시간속보]라면, 수집된 속보들 중 가장 시장 파급력이 큰 핵심 이슈나 특징주 1개를 중심으로 글을 풀어줘.

[유연한 작성 지침 - 매우 중요!]
아래 스타일 가이드는 기계적으로 전부 우겨넣지 말고, 글의 주제(속보 브리핑 vs 개별 종목 분석 vs 재테크·ETF 정보)에 맞춰 가장 자연스럽고 읽기 편하게 유도리 있게 변형해서 적용해줘.

1. 도입부 흐름:
   - 첫 문단은 핵심이 바로 보이는 강렬한 훅으로 시작해줘.
   - 둘째 문단은 왜 지금 이 주제가 중요한지 자연스럽게 설명해줘.
   - 셋째 문단은 “먼저 결론부터 말씀드리면,”으로 시작해서 바쁜 독자가 핵심만 바로 파악할 수 있게 짚어줘.
2. 문체와 호흡:
   - 사람이 직접 쓴 것처럼 짧은 문장 위주로 리듬감 있게 써줘.
   - 한 문단은 1~3문장으로 짧게 끊고, 중요한 문장은 한 줄로 따로 빼서 강조해줘.
   - 말투는 친근하고 전문적인 '니다' 50%, '요' 50% 비율을 자연스럽게 섞어줘. (쉽게 말하면, 결국 여기서 중요한 건, 개인적으로는 같은 표현 자연스럽게 활용)
3. 서식 규칙 (스마트폰/PC 복붙 최적화):
   - 각 섹션 시작 소제목은 # 이모지+숫자. 소제목 형식으로 써줘. (예: # 🔥1. 시장이 갑자기 주목하는 이유)
   - 섹션 사이, 면책사항 앞, 해시태그 앞에는 단독 한 줄로 --- 를 넣어 구분선을 만들어줘.
   - 문단 안의 번호 나열은 ❶, ❷, ❸ 기호를 써줘.
   - 본문에 어울리는 인용구(> 기호 활용)와 핵심 요약용 Markdown 표(2~3열)를 자연스럽게 1개 넣어줘.
   - 본문에 ** 같은 별표 강조 기호나 HTML 태그, 출처, 언론사명, 물결표(~)는 절대 쓰지 마. (숫자 범위는 'A에서 B까지'로 표기)
4. 내용에 맞춘 유연한 마무리:
   - [종목분석]이나 [실시간속보]처럼 투자 판단이 들어가는 글이면 후반부에 핵심 Q&A 3~5가지를 넣어주고, 맨 마지막 문장은 “투자 판단과 책임은 본인에게 있습니다.”로 끝내줘.
   - [정보성] 글(제도, 계좌, ETF 개념 등)이면 억지로 Q&A나 투자 책임 문구를 넣지 말고, 독자에게 도움이 되는 깔끔한 요약 문장으로 마무리해줘.
   - 맨 마지막 줄에는 #서이추 를 포함한 검색용 해시태그 25~30개를 가로로 쭉 이어서 적어줘.

[출력 형식]
첫째 줄에는 반드시 [제목] 핵심 키워드가 들어간 짧고 실제 검색될 만한 제목 만 적고,
둘째 줄부터는 아무런 안내 문구 없이 바로 본문 첫 문단(훅)을 시작해줘.
"""
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    return res.text

def make_thumbnail_from_completed_post(title, completed_body):
    """2단계: 완성된 블로그 글을 분석해 맞춤형 배경 + 핵심 키워드 1000x1000 썸네일 제작"""
    client = genai.Client(api_key=GEMINI_KEY)
    
    # 완성된 글을 읽고 썸네일에 박을 '단 하나의 핵심 단어'와 '배경 그림 영어 프롬프트' 추출
    analysis_prompt = f"""
다음은 방금 완성된 네이버 블로그 글의 제목과 본문입니다.
제목: {title}
본문 앞부분: {completed_body[:1000]}

이 완성된 글에 딱 맞는 1000x1000 썸네일을 만들려고 합니다. 아래 두 줄만 정확히 출력하세요:
[핵심단어] 썸네일 정중앙에 가장 크게 넣을 단 하나의 종목명 또는 핵심 키워드 (예: SK하이닉스, ISA 계좌, 전력설비, 기준금리 등 부연설명 없이 딱 단어만 8자 이내로)
[배경프롬프트] 이 글의 주제와 분위기를 상징하는 세련되고 모던한 다크 톤 3D 금융/산업 일러스트 배경 생성용 영어 프롬프트 (글자나 텍스트가 없는 배경 이미지 묘사, 15단어 이내)
"""
    res = client.models.generate_content(model='gemini-3.8-flash', contents=analysis_prompt).text
    
    center_word = "핵심이슈"
    bg_prompt = "modern dark blue 3d financial stock market abstract background, luxury minimal lighting, no text"
    
    for line in res.strip().split('\n'):
        if line.startswith("[핵심단어]"):
            center_word = line.replace("[핵심단어]", "").strip()
        elif line.startswith("[배경프롬프트]"):
            bg_prompt = line.replace("[배경프롬프트]", "").strip() + ", dark moody lighting, high quality 3d render, strictly no text, no letters"

    # AI 배경 이미지(1000x1000) 실시간 생성 시도 (안정적인 무료 AI 이미지 엔진 활용)
    img = None
    try:
        encoded_bg = urllib.parse.quote(bg_prompt)
        seed = random.randint(1, 99999)
        bg_url = f"https://image.pollinations.ai/prompt/{encoded_bg}?width=1000&height=1000&nologo=true&seed={seed}"
        bg_res = requests.get(bg_url, timeout=15)
        if bg_res.status_code == 200:
            img = Image.open(BytesIO(bg_res.content)).convert("RGB").resize((1000, 1000))
            # 글자가 눈에 확 띄도록 배경 밝기를 35%로 낮춤 (고급스러운 어두운 배경화)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.35)
    except Exception:
        pass

    # 만약 네트워크 지연 등으로 배경 생성 실패 시 고급 그라데이션 다크 배경 자동 생성
    if img is None:
        img = Image.new('RGB', (1000, 1000), color=(15, 22, 42))
        
    draw = ImageDraw.Draw(img)
    
    # 세련된 네온/골드 포인트 프레임 테두리
    draw.rectangle([45, 45, 955, 955], outline=(100, 180, 255), width=6)
    draw.rectangle([62, 62, 938, 938], outline=(255, 255, 255), width=2)
    
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    # 글자 수에 따라 화면에 꽉 차도록 폰트 크기 자동 최적화
    length = len(center_word)
    font_size = 155 if length <= 4 else (125 if length <= 6 else (95 if length <= 9 else 75))
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    # 정중앙 좌표 계산 및 입체 그림자(Drop Shadow) + 흰색 텍스트 렌더링
    try:
        bbox = draw.textbbox((0, 0), center_word, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        w, h = len(center_word) * font_size * 0.85, font_size

    x = (1000 - w) // 2
    y = (1000 - h) // 2 - 15

    # 검은색 외곽선/그림자로 어떤 배경에서도 글자가 선명하게 보이도록 처리
    for dx, dy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 6)]:
        draw.text((x + dx, y + dy), center_word, font=font, fill=(0, 0, 0))
        
    draw.text((x, y), center_word, font=font, fill=(255, 255, 255))
    img.save("thumb.png")
    return center_word

def save_to_naver_blog(title, body):
    """3단계: 네이버 스마트에디터 ONE 접속 및 임시저장"""
    if not NAVER_ID or not NAVER_PW:
        return "⚠️ 네이버 아이디/비번 미설정 (텔레그램 전송만 완료)"
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = context.new_page()
        try:
            page.goto("https://nid.naver.com/nidlogin.login", wait_until="networkidle")
            time.sleep(2)
            page.evaluate(f"document.getElementById('id').value = '{NAVER_ID}';")
            page.evaluate(f"document.getElementById('pw').value = '{NAVER_PW}';")
            time.sleep(1)
            page.click("#log\\.login")
            time.sleep(8)
            
            if "nidlogin" in page.url:
                page.screenshot(path="status.png")
                browser.close()
                return "⚠️ 네이버 해외로그인 차단 또는 보안인증 필요 (캡처 확인)"
                
            page.goto(f"https://blog.naver.com/{NAVER_ID}?Redirect=Write&", wait_until="networkidle")
            time.sleep(6)
            
            frame = page.frame(name="mainFrame")
            if not frame:
                page.screenshot(path="status.png")
                browser.close()
                return "❌ 에디터 프레임 진입 실패"
                
            for selector in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
                try:
                    if frame.locator(selector).is_visible(timeout=2500):
                        frame.locator(selector).click()
                        time.sleep(1)
                except Exception:
                    pass
                    
            frame.locator(".se-documentTitle .se-text-paragraph").click()
            time.sleep(0.5)
            page.keyboard.insert_text(title)
            
            frame.locator(".se-component.se-text .se-text-paragraph").first.click()
            time.sleep(0.5)
            for line in body.split('\n'):
                page.keyboard.insert_text(line)
                page.keyboard.press("Enter")
                time.sleep(0.02)
                
            time.sleep(2)
            frame.locator("button:has-text('저장'), .save_btn__bzc5B").first.click()
            time.sleep(3)
            
            page.screenshot(path="status.png")
            browser.close()
            return "✅ 네이버 블로그 [임시저장] 완료!"
        except Exception as e:
            try: page.screenshot(path="status.png")
            except Exception: pass
            browser.close()
            return f"⚠️ 임시저장 중 예외 발생: {str(e)[:100]}"

def send_telegram(category, thumb_word, title, body, status_msg):
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    caption_text = f"🏷️ 분류: [{category}] ({thumb_word})\n📌 추천 제목:\n{title}\n\n{status_msg}"
    
    with open("thumb.png", "rb") as f:
        requests.post(photo_url, data={"chat_id": TG_CHAT_ID, "caption": caption_text}, files={"photo": f})
        
    if os.path.exists("status.png"):
        with open("status.png", "rb") as f:
            requests.post(photo_url, data={"chat_id": TG_CHAT_ID, "caption": "🖥️ 네이버 에디터 접속 화면"}, files={"photo": f})
            
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
    # 1. 속보 우선 체크 -> 없으면 정보5:종목5 자동 선정
    category, target_topic, news_data = select_topic_and_fetch_news(INPUT_KEYWORD)
    
    # 2. 내용에 맞춰 유연하게 블로그 본문 먼저 완성
    raw_post = write_blog(category, target_topic, news_data)
    
    title_txt = f"{target_topic} 핵심 정리"
    body_lines = []
    for line in raw_post.strip().split('\n'):
        if line.startswith("[제목]"):
            title_txt = line.replace("[제목]", "").strip()
        else:
            body_lines.append(line.replace("**", ""))
            
    final_body = "\n".join(body_lines).strip()
    
    # 3. 완성된 글을 바탕으로 맞춤형 배경 + 핵심 키워드 1000x1000 썸네일 생성
    thumb_word = make_thumbnail_from_completed_post(title_txt, final_body)
    
    # 4. 네이버 블로그 자동 임시저장 및 텔레그램 전송
    status = save_to_naver_blog(title_txt, final_body)
    send_telegram(category, thumb_word, title_txt, final_body, status)
