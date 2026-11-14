import os
import time
import base64
import random
import urllib.parse
import xml.etree.ElementTree as ET
from io import BytesIO
import requests
from bs4 import BeautifulSoup
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

def safe_tg_send(url, data, files=None):
    for attempt in range(2):
        try:
            if files:
                for f in files.values():
                    f.seek(0)
            res = requests.post(url, data=data, files=files, timeout=35)
            if res.status_code == 200:
                return True
        except Exception as e:
            print(f"⚠️ 텔레그램 전송 지연 ({attempt+1}차): {e}", flush=True)
            time.sleep(2)
    return False

def call_gemini_fast(prompt, image_path=None):
    """텍스트 생성 및 영수증 이미지 판독(Vision) 겸용 고속 호출"""
    models = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-2.0-flash"]
    
    parts = [{"text": prompt}]
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64_img}})

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_KEY}"
        payload = {"contents": [{"parts": parts}]}
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue
    raise RuntimeError("Gemini 응답 실패")

def wait_for_telegram_reply(timeout_sec=75):
    """사용자가 텔레그램 채팅창에 입력한 영수증 정답을 실시간으로 읽어옴"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    last_update_id = 0
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("result"):
            last_update_id = r["result"][-1]["update_id"]
    except Exception:
        pass

    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        time.sleep(3)
        try:
            r = requests.get(url, params={"offset": last_update_id + 1, "timeout": 5}, timeout=10).json()
            for item in r.get("result", []):
                last_update_id = item["update_id"]
                msg = item.get("message", {})
                if str(msg.get("chat", {}).get("id")) == str(TG_CHAT_ID):
                    user_text = msg.get("text", "").strip()
                    if user_text:
                        return user_text
        except Exception:
            pass
    return None

def select_topic_and_fetch_news(user_keyword):
    headers = {"User-Agent": "Mozilla/5.0"}
    if user_keyword and user_keyword != "자동":
        return "지정주제", user_keyword, fetch_news_data(user_keyword)

    breaking_query = urllib.parse.quote("속보 특징주 OR 공시 OR 급등")
    naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={breaking_query}&sort=1"
    try:
        res = requests.get(naver_url, headers=headers, timeout=5)
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

    mode = random.choice(["정보성", "종목분석"])
    if mode == "종목분석":
        try:
            fin_res = requests.get("https://finance.naver.com/sise/lastsearch2.naver", headers=headers, timeout=5)
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
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        for item in root.findall('.//item')[:6]:
            articles.append(f"보도: {item.find('title').text}")
    except Exception:
        pass
    try:
        naver_url = f"https://m.search.naver.com/search.naver?where=m_news&query={encoded}&sort=1"
        page = requests.get(naver_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(page.text, 'html.parser')
        for dsc in soup.select('.api_txt_lines.dsc_txt')[:5]:
            articles.append(f"요약: {dsc.get_text(strip=True)}")
    except Exception:
        pass
    return "\n".join(articles) if articles else f"{keyword} 관련 최신 시장 동향"

def write_blog(category, keyword, news_text):
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
셋째 줄: [배경묘사] 이 글의 주제와 분위기를 상징하는 고화질 3D 디지털 아트 일러스트 배경 생성용 영어 프롬프트 (글자 없음, 12단어 이내)
넷째 줄부터: 아무런 안내 문구 없이 바로 본문 첫 문단 시작
"""
    return call_gemini_fast(prompt)

def make_free_ai_thumbnail(thumb_word, bg_prompt):
    img = None
    try:
        full_prompt = f"{bg_prompt}, modern 3d financial digital art, cinematic lighting, dark background, no text"
        encoded_bg = urllib.parse.quote(full_prompt)
        seed = random.randint(1, 99999)
        bg_url = f"https://image.pollinations.ai/prompt/{encoded_bg}?width=1000&height=1000&nologo=true&seed={seed}"
        r = requests.get(bg_url, timeout=8)
        if r.status_code == 200 and len(r.content) > 5000:
            img = Image.open(BytesIO(r.content)).convert("RGB").resize((1000, 1000))
            img = ImageEnhance.Brightness(img).enhance(0.45)
    except Exception:
        pass

    if img is None:
        img = Image.new('RGB', (1000, 1000))
        draw_bg = ImageDraw.Draw(img)
        for y in range(1000):
            draw_bg.line([(0, y), (1000, y)], fill=(int(14 + y*0.02), int(22 + y*0.035), int(45 + y*0.06)))
        draw_bg.ellipse([120, 120, 880, 880], outline=(40, 75, 130), width=4)

    draw = ImageDraw.Draw(img)
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
    for dx, dy in [(-6, -6), (6, -6), (-6, 6), (6, 6), (0, 8)]:
        draw.text((x + dx, y + dy), thumb_word, font=font, fill=(0, 0, 0))
    draw.text((x, y), thumb_word, font=font, fill=(255, 255, 255))
    
    abs_path = os.path.abspath("thumb.jpg")
    img.save(abs_path, format="JPEG", quality=92)
    return abs_path

def send_post_to_telegram(category, thumb_word, title, body, thumb_path):
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    caption_text = f"🏷️ 분류: [{category}] ({thumb_word})\n📌 제목:\n{title}"
    
    with open(thumb_path, "rb") as f:
        safe_tg_send(photo_url, data={"chat_id": TG_CHAT_ID, "caption": caption_text}, files={"photo": f})
        
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    max_len = 3800
    if len(body) <= max_len:
        safe_tg_send(msg_url, data={"chat_id": TG_CHAT_ID, "text": body})
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
            safe_tg_send(msg_url, data={"chat_id": TG_CHAT_ID, "text": part.strip()})
            time.sleep(0.5)

def save_to_naver_blog_with_image(title, body, thumb_abs_path):
    if not NAVER_ID or not NAVER_PW:
        return "ℹ️ 네이버 ID/PW 미입력 상태"
        
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul"
        )
        page = context.new_page()
        page.set_default_timeout(12000)
        
        try:
            page.goto("https://nid.naver.com/nidlogin.login?locale=ko_KR", wait_until="domcontentloaded")
            time.sleep(2)
            
            # 1차 로그인 시도: 실제 사람처럼 한 글자씩 타이핑
            id_box = page.locator("input#id, input[name='id']").first
            id_box.click()
            id_box.type(NAVER_ID, delay=80)
            time.sleep(0.5)
            
            pw_box = page.locator("input#pw, input[name='pw']").first
            pw_box.click()
            pw_box.type(NAVER_PW, delay=80)
            time.sleep(0.5)
            page.keyboard.press("Enter")
            time.sleep(5)
            
            # 만약 영수증 캡차 화면이 떴다면? -> 1단계: AI가 먼저 풀기 / 2단계: 텔레그램으로 물어보기
            if "nidlogin" in page.url:
                page.screenshot(path="captcha.jpg", type="jpeg", quality=85)
                
                # (1) Gemini Vision AI에게 영수증 문제 풀어달라고 요청
                try:
                    ai_ans = call_gemini_fast(
                        "이 네이버 로그인 화면에 있는 영수증 이미지와 질문을 읽고, 빈칸에 들어갈 정답(숫자 또는 단어)만 딱 출력해줘. 단위나 부연설명 없이 오직 정답 글자만 출력해.",
                        image_path="captcha.jpg"
                    )
                    ai_ans = ai_ans.replace(" ", "").replace("\n", "")
                    print(f"🤖 AI가 추론한 영수증 정답: {ai_ans}", flush=True)
                    
                    pw_box = page.locator("input#pw, input[name='pw']").first
                    pw_box.click()
                    pw_box.fill(NAVER_PW)
                    
                    cap_box = page.locator("input#captcha, input[name='captcha']").first
                    cap_box.click()
                    cap_box.fill(ai_ans)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(5)
                except Exception as ce:
                    print(f"AI 캡차 풀이 건너뜀: {ce}", flush=True)

            # (2) 그래도 아직 영수증 화면이라면 -> 내 텔레그램으로 사진 보내고 내가 친 정답 받아서 입력!
            if "nidlogin" in page.url:
                page.screenshot(path="captcha2.jpg", type="jpeg", quality=85)
                with open("captcha2.jpg", "rb") as f:
                    safe_tg_send(
                        photo_url,
                        data={
                            "chat_id": TG_CHAT_ID,
                            "caption": "🧾 [영수증 퀴즈 발생!]\n지금 70초 안에 이 채팅방에 위 영수증 문제의 정답만 딱 입력해 주세요! (예: 4500 또는 떡볶이)"
                        },
                        files={"photo": f}
                    )
                user_ans = wait_for_telegram_reply(timeout_sec=70)
                if user_ans:
                    safe_tg_send(msg_url, data={"chat_id": TG_CHAT_ID, "text": f"👌 입력하신 정답 '{user_ans}'(으)로 로그인을 돌파합니다!"})
                    pw_box = page.locator("input#pw, input[name='pw']").first
                    pw_box.click()
                    pw_box.fill(NAVER_PW)
                    
                    cap_box = page.locator("input#captcha, input[name='captcha']").first
                    cap_box.click()
                    cap_box.fill(user_ans)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(5)

            try:
                if page.locator("#new\\.dontsave, a#new\\.dontsave").is_visible(timeout=2000):
                    page.locator("#new\\.dontsave, a#new\\.dontsave").click()
                    time.sleep(2)
            except Exception:
                pass

            if "nidlogin" in page.url:
                page.screenshot(path="status.jpg", type="jpeg", quality=80)
                browser.close()
                return "❌ 영수증 정답 불일치 또는 로그인 제한으로 진입하지 못했습니다."
                
            # 스마트에디터 진입
            page.goto(f"https://blog.naver.com/{NAVER_ID}?Redirect=Write&", wait_until="domcontentloaded")
            time.sleep(5)
            
            frame = page.frame(name="mainFrame")
            if not frame:
                page.goto(f"https://blog.naver.com/PostWriteForm.naver?blogId={NAVER_ID}", wait_until="domcontentloaded")
                time.sleep(4)
                frame = page.frame(name="mainFrame") or page.main_frame
                
            for selector in [".se-popup-button-cancel", ".se-help-panel-close-button"]:
                try:
                    if frame.locator(selector).is_visible(timeout=1500):
                        frame.locator(selector).click()
                        time.sleep(0.5)
                except Exception:
                    pass
                    
            frame.locator(".se-documentTitle .se-text-paragraph").first.click()
            time.sleep(0.5)
            page.keyboard.insert_text(title)
            
            frame.locator(".se-component.se-text .se-text-paragraph").first.click()
            time.sleep(0.5)
            try:
                with page.expect_file_chooser(timeout=4000) as fc_info:
                    frame.locator("button.se-image-toolbar-button, button[data-name='image']").first.click()
                file_chooser = fc_info.value
                file_chooser.set_files(thumb_abs_path)
                time.sleep(3)
                page.keyboard.press("Enter")
                time.sleep(0.5)
            except Exception:
                pass
                
            page.keyboard.insert_text(body)
            time.sleep(2)
            
            frame.locator("button:has-text('저장'), .save_btn__bzc5B").first.click()
            time.sleep(3)
            
            page.screenshot(path="status.jpg", type="jpeg", quality=80)
            browser.close()
            return "✅ 네이버 블로그 [맨 위 썸네일 + 아래 본문] 자동 임시저장 완료!"
        except Exception as e:
            try: page.screenshot(path="status.jpg", type="jpeg", quality=80)
            except Exception: pass
            browser.close()
            return f"⚠️ 네이버 임시저장 중 멈춤: {str(e)[:90]}"

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
    
    thumb_path = make_free_ai_thumbnail(thumb_word, bg_prompt)
    send_post_to_telegram(category, thumb_word, title_txt, final_body, thumb_path)
    
    status_msg = save_to_naver_blog_with_image(title_txt, final_body, thumb_path)
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    safe_tg_send(msg_url, data={"chat_id": TG_CHAT_ID, "text": status_msg})
    
    if os.path.exists("status.jpg"):
        photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        with open("status.jpg", "rb") as f:
            safe_tg_send(photo_url, data={"chat_id": TG_CHAT_ID, "caption": "🖥️ 네이버 에디터 실행 화면"}, files={"photo": f})
    print("🎉 모든 작업이 완료되었습니다!", flush=True)
