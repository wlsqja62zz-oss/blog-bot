import os
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from google import genai
from PIL import Image, ImageDraw, ImageFont

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
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

참고할 최신 시장 뉴스 데이터 (출처나 언론사명은 본문에 절대 언급하지 말고 팩트 파악용으로만 참고할 것):
{news_text}

----------------------------------------------
위 주제와 최신 뉴스 흐름을 바탕으로 네이버 블로그용 주식, ETF, 산업, 테마, 재테크 글을 작성해줘. 글쓰기박스 사용금지.
입력값은 개별 종목명일 수도 있고, ETF, 산업, 테마, 수혜주, 시장 이슈, 투자 포인트 같은 넓은 주제일 수도 있다.
입력한 주제가 넓더라도 백과사전식 설명이나 딱딱한 보고서형 글로 쓰지 말고, 지금 시장에서 왜 중요한지부터 먼저 보이게 써줘.

글은 사람이 직접 쓴 것처럼 자연스럽고 읽기 쉽게 써줘. 너무 딱딱한 교과서체, 보고서체, AI 같은 문장은 피하고 실제 블로거가 쓴 느낌으로 작성해줘. 초보 투자자도 이해할 수 있게 쉽게 설명하되, 너무 가볍거나 유치하게 흐르지 않게 균형 있게 써줘.

네이버 블로그 SEO도 함께 고려해서 작성해줘. 입력한 주제의 핵심 키워드를 제목, 도입부, 본문 중간, 마무리에 자연스럽게 넣어줘. 단, 키워드를 억지로 반복하지 말고 사람이 읽었을 때 자연스럽게 보이게 써줘.
제목은 짧게 작성해줘. 제목에는 핵심 키워드가 반드시 들어가야 하고, 가능하면 검색 사용자가 실제로 찾을 만한 표현으로 써줘. 너무 추상적인 제목보다 실제 검색될 표현을 우선해줘.
본문 첫 2문단 안에도 핵심 키워드를 자연스럽게 넣어줘. 본문 중간에는 핵심 키워드와 연관 키워드를 적절히 섞어줘. 마무리에서도 핵심 키워드를 한 번 자연스럽게 다시 넣어줘. 해시태그 역시 핵심 키워드와 연관 키워드 중심으로 작성해줘. 검색 유입을 고려하되, 키워드만 억지로 반복하는 글은 쓰지 말아줘.

검색 사용자가 궁금해할 만한 흐름으로 써줘. 예를 들면 왜 중요한지, 지금 봐야 하는 이유가 뭔지, 실제 수혜가 가능한 쪽은 어디인지, 리스크는 무엇인지, 지금 구간이 어떤지 같은 질문에 답하는 방식으로 자연스럽게 써줘.

글 시작은 반드시 아래 흐름을 지켜줘.
첫 문단은 주제의 핵심이 바로 보이는 훅으로 시작해줘.
그 다음 문단에서는 왜 이 내용을 찾게 됐는지, 왜 요즘 이 주제가 중요해졌는지, 왜 사람들이 궁금해하는지를 짧고 자연스럽게 설명해줘. 이 부분에도 핵심 키워드를 자연스럽게 포함해줘.
그 다음 문단은 반드시 “먼저 결론부터 말씀드리면,”으로 시작해줘. 이 문단에서는 설명을 길게 끌지 말고, 가장 중요한 핵심 포인트를 먼저 바로 제시해줘. 독자가 초반 몇 문단만 읽어도 글 전체 핵심을 이해할 수 있게 써줘. 도입부는 배경 설명부터 길게 하지 말고, 반드시 핵심이 먼저 보이는 방식으로 써줘.

글은 고정 목차형으로 쓰지 말고, 우선순위형 구조로 작성해줘. 즉, 회사소개부터 기계적으로 시작하지 말고 입력한 주제에서 지금 가장 중요한 포인트를 맨 위로 먼저 배치해줘.
글 흐름은 아래처럼 자연스럽게 구성해줘: 핵심 포인트 -> 왜 중요한지 -> 근거 설명 -> 실제 수혜 구조 또는 체크포인트 -> 현실적인 결론.
아래 요소들은 필요하면 활용하되, 반드시 순서대로 나열하지는 말아줘(참고 재료일 뿐이고 가장 중요한 내용을 먼저 배치해서 자연스럽게 재구성): 핵심요약, 회사소개 또는 테마 소개, 주가 위치 또는 시장 내 위치, 실적 흐름 또는 산업 흐름, 체크포인트, 상승 시나리오와 하락 시나리오, 최근 호재 뉴스와 리스크 분석, 한마디 요약.

전체 글자 수는 가능하면 2천자 이상으로 작성해줘. 정보성 글은 1000자 이상이면 돼. 다만 글자 수를 맞추기 위해 불필요한 정보나 중복 설명을 억지로 넣지는 말아줘. 핵심 내용을 자연스럽게 풀었는데 2천자에 못 미치면, 억지로 분량을 늘리지 않아도 돼.

문체는 길게 설명하는 방식보다 짧은 문장 위주로 써줘. 반드시 아래 규칙을 지켜줘:
- 한 문장은 되도록 짧게 쓸 것
- 한 문단에는 하나의 핵심만 담을 것
- 문단은 짧게 끊을 것 (한 문단은 가능하면 1문장에서 3문장 정도로 짧게 유지)
- 중요한 문장은 한 줄로 따로 빼서 강조할 것
- 같은 문장 구조를 반복하지 말 것
- 정보만 나열하지 말고, 왜 중요한지 바로 해석해줄 것
- 실제 블로그처럼 리듬감 있게 쓸 것
- 너무 설명문처럼 길어지지 않게 할 것
- “입니다만”이 반복되는 딱딱한 문장은 피할 것
- AI가 쓴 것처럼 뻔한 결론 반복은 피할 것

아래 표현은 자연스럽게 섞어줘:
쉽게 말하면 / 결국 여기서 중요한 건 / 한마디로 / 즉 / 개인적으로는 / 제 생각에는 / 체크해볼 부분은 / 이 구간에서는
문체는 “니다”와 “요”를 자연스럽게 섞어줘. 전체적으로 “니다” 50%, “요” 50% 정도 느낌이면 좋아. 입니다~, 이에요~, ....!, !!, 이모지 등 활용해서 사람이 쓰는 듯한 말투로 써줘.

PC뿐 아니라 휴대폰으로도 네이버 블로그에 바로 붙여넣을 수 있어야 해. 복사하기 어려운 특수기호나 깨지는 구분선은 사용하지 말아줘.
구분선 규칙은 반드시 아래처럼 지켜줘:
- 각 섹션 사이, 면책사항 앞, 해시태그 앞에는 네이버 블로그 회색 가로선처럼 보이도록 Markdown 구분선인 --- 를 단독 한 줄로 넣어줘.
- --- 는 코드블럭 안에 넣지 말고 실제 본문 중간에 바로 출력해줘.
- --- 앞뒤에는 빈 줄을 넣어줘.
- ────────────────── 나 ━━━━━━━━ 같은 특수문자 구분선은 절대 쓰지 마.
- 글 전체를 코드블럭으로 감싸지 말고, 네이버 블로그에 바로 복사 가능한 본문 형태로 작성해줘.

소제목 규칙은 반드시 아래처럼 지켜줘:
- 각 섹션이 시작될 때 들어가는 소제목은 글씨가 크게 보이도록 반드시 Markdown 제목 형식으로 써줘.
- 형식: # 이모지+숫자. 소제목 (예시: # 🚚1. CU 점주들이 왜 강경하게 나섰을까?)
- 소제목에는 항상 주제와 어울리는 이모지를 하나 넣어줘. 문장마다 이모지를 넣지 말고, 섹션 제목이나 강조 포인트에만 자연스럽게 사용해줘.
- 소제목 다음에는 빈 줄을 충분히 넣고 본문을 시작해줘.
- 문단 속 맨 앞에 숫자 1, 2, 3, 4, 5를 써야 할 경우에는 가능하면 ❶, ❷, ❸, ❹, ❺, ❻, ❼, ❽, ❾, ❿ 같은 형태로 정리해줘.

입력값 성격별 반영 사항:
1) 입력값이 종목이면: 지금 주가가 고점권, 중간권, 바닥권 중 어디에 가까운지 의견 제시 / 실적 흐름은 과거, 현재, 미래가 자연스럽게 이어지게 설명 / PBR, PER, ROE 같은 지표는 단순 나열 말고 현재 주가 해석 중심으로 설명 / 호재와 리스크는 반드시 구분 / 지금 주가가 움직이는 이유가 실적인지, 뉴스인지, 수급인지, 업황인지 먼저 판단해서 그 순서대로 설명 / 무조건 좋다고 하지 말고 실제 확인이 필요한 부분을 같이 짚어줘 / 종목명과 핵심 연관 키워드를 본문 중간에도 자연스럽게 다시 넣어줘 / 해시태그는 종목 이름 뒤에 주가, 호가, 목표가, 전망 같은 검색형 키워드를 붙여서 구성.
2) 입력값이 ETF면: 왜 이 ETF를 찾는 사람이 많은지 먼저 설명 / 월배당, 분배금, 자산 구성, 변동성, 듀레이션, 보수, 구조적 특징 중 핵심부터 설명 / 많이 준다보다 덜 흔들린다, 현금흐름이 안정적이다, 주가 변동이 크다 같은 본질을 먼저 설명 / 수익률만 강조하지 말고 가격 변동성과 구조도 함께 설명 / 어떤 투자자에게 맞고, 어떤 경우엔 조심해야 하는지 현실적으로 정리 / ETF명과 핵심 연관 키워드를 본문 중간에도 자연스럽게 다시 넣어줘.
3) 입력값이 테마, 산업, 밸류체인, 수혜주 정리면: 지금 시장이 어디를 보고 있는지 먼저 설명 / 그런데 실제로 다음에 붙는 포인트가 무엇인지 흐름 전환형으로 써줘 / 핵심 테마와 확장 테마를 구분 / 직접 수혜, 간접 수혜, 기대 수혜를 구분 / 확정 수혜와 기대감만 있는 수혜를 반드시 나눠서 설명 / 누가 실제 실적을 가져갈 가능성이 큰지와 누가 먼저 주가가 반응할 수 있는지를 구분 / 지금이 초입인지, 과열인지, 확인이 더 필요한 구간인지 의견 제시 / 마지막은 공부할 때인지, 추격할 때인지, 확인이 먼저인지 현실적으로 정리.

필수 주의사항:
- 확인 안 되는 수치나 정보는 절대 추정하지 말 것 (최신 기준으로 확인된 내용만 반영)
- 애매한 뉴스는 억지로 넣지 말 것
- 숫자 범위는 반드시 “A에서 B까지” 형식으로 표기할 것 (물결표 ~ 는 절대 사용하지 말 것)
- 숫자가 모호하면 보수적으로 표현하거나 생략할 것
- 단정적인 표현보다 근거 중심으로 설명할 것 (무조건 낙관, 무조건 비관 금지)
- 본문에 출처, 링크, 언론사명, 괄호형 citation을 절대절대 표시하지 마! 참고한 내용은 출처 없이 자연스럽게 본문에 녹여 써줘.
- HTML 태그(table, tr, td, style= 등)는 절대 사용하지 마.
- 인용구(> 활용)도 자연스럽게 넣어주고, 표도 넣어줘. 표는 반드시 Markdown 표 형식으로만 작성하되 2열 또는 3열까지만 사용하고 각 칸의 문장은 짧게 써줘. 표를 코드블럭으로 감싸지 말고 본문에 바로 출력해줘.
- 본문에서 ** 같은 마크다운 굵게 강조표시는 쓰지 마. (단, Q&A 질문 제목은 눈에 띄게 굵게 하거나 구분해줘)
- 본문 위에 쓸데없는 말(작성기준, 확인기준 등 안내 문구)은 다 빼고 바로 본문 훅부터 시작해줘.
- 투자 판단이나 종목 분석, 수혜주 해설, 매매 관점이 포함된 투자글이라면 본문 후반에 투자자들이 궁금할 만한 Q&A 5가지를 넣어주고, 글의 맨 마지막 문장은 반드시 “투자 판단과 책임은 본인에게 있습니다.”로 끝내줘. (정보 전달 중심 글이면 Q&A 없이 자연스러운 정리 문장으로 마무리)
- 맨 아래에는 관련 해시태그 30개를 가로로 쭉 이어서 써줘 (세로로 길게 쓰지 마). 반드시 #서이추 를 포함해줘.

[시스템 자동 분리용 출력 규격 - 가장 중요!]
프로그램이 썸네일과 제목을 분리할 수 있도록 글의 맨 처음 두 줄만 아래 형식으로 적고, 셋째 줄부터는 제목이나 인사말 없이 바로 본문 첫 문단(훅)을 시작해줘:
[썸네일] 썸네일에 크게 넣을 오직 단 하나의 핵심 종목명 또는 핵심 키워드 (다른 부연 설명 텍스트 절대 금지)
[제목] 핵심 키워드가 포함된 짧고 강렬한 실제 검색용 제목
(셋째 줄부터 바로 본문 시작)
"""
    res = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    return res.text

def make_thumbnail(text):
    # 요청하신 1000x1000 사이즈 및 종목명 단독 배치
    img = Image.new('RGB', (1000, 1000), color=(18, 26, 48))
    draw = ImageDraw.Draw(img)
    
    # 세련된 이중 테두리 배경 연출
    draw.rectangle([45, 45, 955, 955], outline=(90, 165, 255), width=8)
    draw.rectangle([65, 65, 935, 935], outline=(45, 85, 140), width=2)
    
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    # 글자 길이에 맞춰 꽉 차게 보이도록 폰트 크기 자동 조절
    font_size = 130 if len(text) <= 5 else (100 if len(text) <= 8 else 75)
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    # 텍스트가 길 경우에만 2줄로 나누고, 종목명은 한 줄 정중앙에 큼직하게 배치
    words = text.split()
    lines, cur = [], ""
    max_len = 6 if len(text) <= 10 else 8
    for w in words:
        if len(cur + " " + w) <= max_len:
            cur += (" " + w if cur else w)
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    
    line_height = font_size + 30
    total_height = len(lines) * line_height
    y = (1000 - total_height) // 2
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
        except:
            w = len(line) * font_size * 0.8
        x = (1000 - w) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height
        
    img.save("thumb.png")

def send_telegram(title, body):
    # 1. 1000x1000 썸네일 전송 (캡션에 짧은 추천 제목 표시)
    photo_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    with open("thumb.png", "rb") as f:
        requests.post(
            photo_url,
            data={"chat_id": TG_CHAT_ID, "caption": f"📌 추천 제목 (짧은 버전):\n{title}"},
            files={"photo": f}
        )
        
    # 2. 본문 전송 (2,000자 이상 긴 글일 경우 문단 단위로 나누어 잘림 없이 연속 전송)
    msg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    max_len = 3800
    if len(body) <= max_len:
        requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": body})
    else:
        parts = []
        current = ""
        for line in body.split('\n'):
            if len(current) + len(line) + 1 > max_len:
                parts.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            parts.append(current)
        for part in parts:
            requests.post(msg_url, data={"chat_id": TG_CHAT_ID, "text": part.strip()})

if __name__ == "__main__":
    news = get_news_without_api(KEYWORD)
    if news:
        raw = write_blog(KEYWORD, news)
        thumb_txt = KEYWORD
        title_txt = f"{KEYWORD} 주가 전망 및 핵심 체크포인트"
        body_lines = []
        
        for line in raw.strip().split('\n'):
            if line.startswith("[썸네일]"):
                thumb_txt = line.replace("[썸네일]", "").strip()
            elif line.startswith("[제목]"):
                title_txt = line.replace("[제목]", "").strip()
            else:
                # 프롬프트 규칙대로 본문 내 불필요한 ** 강조 기호가 남아있다면 자동 제거
                clean_line = line.replace("**", "")
                body_lines.append(clean_line)
                
        make_thumbnail(thumb_txt)
        send_telegram(title_txt, "\n".join(body_lines).strip())
