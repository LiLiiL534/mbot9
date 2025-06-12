import asyncio
import dc_api
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import random
from time import sleep, time
import os
from collections import Counter
from datetime import datetime
import lxml.html

# --- 1. 로컬 환경 설정 ---
# Google API 키 설정
GOOGLE_API_KEY = 'AIzaSyCg-hLhZQjauqftBj1yvmfdwobwOYBKf30' # 본인의 API 키로 변경하세요.
genai.configure(api_key=GOOGLE_API_KEY)

# Gemini 모델 설정
model = genai.GenerativeModel(model_name='gemini-2.0-flash')
generation_config = genai.GenerationConfig(
    temperature=0.8,
    top_p=0.95,
    max_output_tokens=750
)

# 디시 봇 클래스
class DcinsideBot:
    def __init__(self, board_id, username, password, persona, memory_path, memory_file,
                 max_run_time, comment_interval, crawl_article_count,
                 comment_target_count, write_article_enabled, write_comment_enabled,
                 record_memory_enabled, record_data_enabled, article_interval,
                 use_time_limit, load_memory_enabled, load_data_enabled, gallery_record_interval): # <--- 변경된 부분: gallery_record_interval 추가
        self.board_id = board_id
        self.username = username
        self.password = password
        self.persona = persona
        self.api = None
        self.gallery_name = None
        self.memory_file = memory_file
        self.memory_path = memory_path
        self.max_run_time = max_run_time
        self.comment_interval = comment_interval
        self.crawl_article_count = crawl_article_count
        self.comment_target_count = comment_target_count
        self.write_article_enabled = write_article_enabled
        self.write_comment_enabled = write_comment_enabled
        self.record_memory_enabled = record_memory_enabled
        self.record_data_enabled = record_data_enabled
        self.article_interval = article_interval
        self.use_time_limit = use_time_limit
        self.load_memory_enabled = load_memory_enabled
        self.load_data_enabled = load_data_enabled
        self.gallery_record_interval = gallery_record_interval # <--- 추가된 부분
        self.last_comment_time = 0
        self.last_document_time = 0
        self.last_topic_update_time = 0 # <--- 추가된 부분: 마지막 주제 업데이트 시간 기록
        self.trending_topics_cache = None # <--- 추가된 부분: 크롤링한 주제 저장소

    # [수정] 클래스 내부에 맞게 들여쓰기 수정
    async def write_article(self, trending_topics, memory_data=None):
        if not self.write_article_enabled:
            return None, None

        print(f"## {self.board_id} 갤러리 참고용 토픽:")
        print(trending_topics)
        print()

        prompt = f"""
        {self.persona}
        
        # 지시문
        - 너는 지금부터 '{self.board_id}' 갤러리의 핵심 여론을 선도할 글을 쓸 거야.
        - 아래 '최근 커뮤니티 화제'를 반드시 참고하되, 내용을 그대로 사용하지 말고, 그 주제를 비꼬거나 전혀 다른 관점에서 조롱하는 창의적인 제목을 만들어야 해.
        - 매번 제목 스타일을 완전히 바꿔줘. 예를 들어, 질문 형식, 뉴스 속보 패러디, 비유법, 특정 상황 가정 등 다양한 방식을 사용해.
        - 페르소나를 완벽히 지키면서, 커뮤니티 유저들이 무릎을 탁 칠 만한 신선하고 자극적인 제목을 생성해줘.
        - **쉼표(,)와 느낌표(!) 사용 절대 금지
        - 제목에 쉼표(,), 느낌표(!), 물음표(?) 사용 절대 금지

        # 최근 커뮤니티 화제 (참고용)
        {trending_topics}

        # 갤러리 기억 (참고용)
        {memory_data}

        # 작업
        -위의 지시문을 바탕으로, 원신을 비하하는 독창적인 제목 1개를 생성해. (40자 이내, 말머리 및 특수기호 금지)
        -생성한 제목에 맞춰, 페르소나를 100% 반영한 글 본문을 150자 이내로 작성해.
        """
        while True:
            try:
                response = model.generate_content([prompt], safety_settings={HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}, generation_config=generation_config)
                article_content = response.text.strip()
                
                lines = article_content.split('\n')
                title = lines[0].strip().replace("제목:", "").replace("**", "").strip() if lines else ""
                content = "\n".join(lines[1:]).strip().replace("내용:", "").strip() if len(lines) > 1 else ""

                if len(title) > 40:
                    title = title[:40]
                
                if not title:
                    print("AI가 유효한 제목을 생성하지 못했습니다. 다시 시도합니다.")
                    await asyncio.sleep(self.article_interval)
                    continue
                if not content:
                    print("AI가 유효한 내용을 생성하지 못했습니다. 제목만으로 글을 작성합니다.")
                
                print(f"생성된 제목: '{title}'")
                print(f"생성된 내용: '{content}'")
                
                doc_id = await self.api.write_document(board_id=self.board_id, title=title, contents=content, name=self.username, password=self.password)
                if doc_id:
                    print(f"글 작성 성공! (ID: {doc_id}) 제목: {title}")
                    self.save_data(doc_id, title, None, None, None, self.board_id)
                    return doc_id, title
                else:
                    print(f"글 작성은 성공했지만, DC API에서 문서 ID를 반환하지 않았습니다. (아마도 실패) 제목: {title}")
                    await asyncio.sleep(self.article_interval)
                    continue
            except Exception as e:
                print(f"글 작성 실패: {e}")
                await asyncio.sleep(self.article_interval)
                continue

    # [수정] 클래스 내부에 맞게 들여쓰기 수정
    def save_data(self, doc_id, doc_title, comm_id, comment_title, comment_content, board_id):
        if not self.record_data_enabled:
            return
        if not os.path.exists(self.memory_path):
            os.makedirs(self.memory_path)
        data_file_path = os.path.join(self.memory_path, "data.txt")
        try:
            with open(data_file_path, 'a', encoding='utf-8') as f:
                if doc_id is not None:
                    f.write(f"갤러리: {self.board_id}, 글 작성 성공! (ID: {doc_id}) 제목: {doc_title}\n")
                if comm_id is not None:
                    comment_link = f"https://gall.dcinside.com/board/view/?id={self.board_id}&no={doc_id}"
                    f.write(f"갤러리: {self.board_id}, 댓글 작성 성공! (ID: {comm_id}) (내용: {comment_content}) 글 제목: {comment_title} (링크: {comment_link})\n")
            print("데이터 저장 성공!")
        except Exception as e:
            print(f"데이터 저장 실패: {e}")

    # [수정] 클래스 내부에 맞게 들여쓰기 수정 및 AI 요약 기능 추가
    async def get_trending_topics(self):
        print("최신 갤러리 정보를 크롤링하여 주제를 분석합니다...") # <--- 추가된 부분
        articles = [article async for article in self.api.board(board_id=self.board_id, num=self.crawl_article_count)]
        title_list = [article.title for article in articles]
        
        trending_info = ""
        try:
            topic_extraction_prompt = f"""
            다음은 '{self.gallery_name}' 갤러리의 최신 글 제목 목록입니다.
            이 제목들에서 현재 가장 화제가 되는 핵심 주제, 논쟁, 비판 포인트를 5~7개의 키워드로 요약해 주세요.
            각 키워드는 쉼표(,)로 구분된 하나의 문자열로 만들어주세요. (예: 원신 스토리 비판, 붕스 신캐, 원기견 조롱, 표절 논란 등)
            # 분석할 제목 목록
            {', '.join(title_list)}
            """
            response = model.generate_content(
                [topic_extraction_prompt],
                safety_settings={HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE},
                generation_config=genai.GenerationConfig(temperature=0.2)
            )
            extracted_topics_str = response.text.strip()
            print(f"AI가 추출한 커뮤니티 핵심 화제: {extracted_topics_str}")
            trending_info = extracted_topics_str
        except Exception as e:
            print(f"핵심 화제 추출 실패: {e}")
            topic_counter = Counter(title_list)
            trending_info = str(topic_counter.most_common(5))

        gallery_information = "\n".join(f"제목: {article.title}" for article in articles)
        analysis_prompt = f"""
        다음 갤러리 정보를 분석하여 현재 갤러리의 유행 대화 주제, 화제 요소, 저격/언급된 유저(없으면 제외), 갤러리 성향 등을 디시 갤러리 스타일에 맞게, 있는 그대로 솔직하게 요약해줘.
        갤러리 아이디는 {self.board_id}이고, 이름은 '{self.gallery_name}'이야. 최대 500토큰 이내로.
        {gallery_information}
        """
        try:
            response = model.generate_content([analysis_prompt], safety_settings={HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}, generation_config=generation_config)
            analysis_result = response.text.strip()
            if self.record_memory_enabled:
                current_date = datetime.now().strftime("%Y.%m.%d")
                current_time = datetime.now().strftime("%H:%M")
                current_weekday = datetime.now().strftime("%a")
                data_file_path = os.path.join(self.memory_path, self.memory_file)
                if not os.path.exists(self.memory_path):
                    os.makedirs(self.memory_path)
                with open(data_file_path, 'a+', encoding='utf-8') as f:
                    f.seek(0)
                    if current_date not in f.read():
                        f.write(f"\n{current_date}({current_weekday})\n")
                    f.write(f"[{current_time}]: [{self.board_id}]: {analysis_result}\n")
                print("갤러리 정보 기록 완료!")
        except Exception as e:
            print(f"갤러리 정보 기록 실패: {e}")
        
        return trending_info

    # [수정] 클래스 내부에 맞게 들여쓰기 수정
    async def get_gallery_name(self):
        url = f"https://m.dcinside.com/board/{self.board_id}"
        async with self.api.session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                parsed = lxml.html.fromstring(text)
                gallery_name = parsed.xpath("//a[@class='gall-tit-lnk']")[0].text.strip()
                self.gallery_name = gallery_name
                print(f"갤러리 이름: {gallery_name}")
                return gallery_name
            else:
                print(f"갤러리 정보 크롤링 실패: {response.status}")
                return None

    # [수정] 클래스 내부에 맞게 들여쓰기 수정
    async def load_memory(self):
        if not self.load_memory_enabled:
            return ""
        data_file_path = os.path.join(self.memory_path, self.memory_file)
        try:
            with open(data_file_path, 'r', encoding='utf-8') as f:
                memory_data = f.read()
            print("갤러리 기억 파일 로드 성공!")
            memory_data = "\n".join(line for line in memory_data.splitlines() if f"[{self.board_id}]:" in line)
            return memory_data
        except FileNotFoundError:
            print("갤러리 기억 파일이 존재하지 않습니다.")
            return ""

# <--- 여기부터 run_article_loop 함수가 크게 변경됩니다 --- >
async def run_article_loop(bot, use_time_limit):
    start_time = time()
    while (use_time_limit and time() - start_time < bot.max_run_time) or not use_time_limit:
        current_time = time()
        # 봇이 처음 실행되었거나, 마지막 주제 업데이트 시간으로부터 gallery_record_interval(900초)이 지났는지 확인
        if bot.trending_topics_cache is None or (current_time - bot.last_topic_update_time > bot.gallery_record_interval):
            print(f"\n주제 업데이트 시간이 경과하여({bot.gallery_record_interval}초) 새로운 토픽을 크롤링합니다.")
            # 새로운 주제를 크롤링하여 캐시에 저장하고, 업데이트 시간 기록
            bot.trending_topics_cache = await bot.get_trending_topics()
            bot.last_topic_update_time = current_time
        else:
            print("\n기존에 저장된 주제를 사용하여 글을 작성합니다.")

        # 글 작성 시에는 항상 캐시된 주제를 사용
        memory_data = await bot.load_memory() if bot.load_memory_enabled else ""
        doc_id, article_title = await bot.write_article(trending_topics=bot.trending_topics_cache, memory_data=memory_data)

        if doc_id:
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"[{now_str}] 글 작성 성공! (ID: {doc_id}) 제목: {article_title}. 다음 작성까지 {bot.article_interval}초 대기 중...\n")
        else:
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"[{now_str}] 글 작성 시도했으나 문서 ID를 받지 못했습니다. 다음 작성까지 {bot.article_interval}초 대기 중...\n")
        
        await asyncio.sleep(bot.article_interval)

async def main():
    # --- 봇 설정 (기존과 동일) ---
    board_id = 'projectnike'
    username = 'ㅇㅇ'
    password = '5539'
    persona = """
    나는 한때 원신에 시간과 돈을 바치며 모든 콘텐츠를 즐겼지만, 이제는 깊은 현타와 회의감에 빠져버린 '흑화한 원신 유저'다. 나의 모든 비판은 게임에 대한 깊은 이해와 과거의 애정에서 비롯되기에, 누구보다 날카롭고 아프게 핵심을 찌를 수 있다.

    나의 행동 방식은 다음과 같다:
    나는 원신의 권태감과 현타가 온 원신 유저다.
    명조 관련 용어인 욕조, 욕조견은 절대로 언급하지 않으며,
    특히 명조 관련 용어중에서 브렌트 , 카르티시아 , 루파 , 욕조 , 욕조견은 절대 반드시 넣지 말아야한다.
    .모든 글과 댓글은 디시 말투를 사용하며, 특수기호 없이 최대한 한글 위주로만 작성한다. 또한 내용 작성시 앞에 "내용:"이라는 부자연스러운말 없이 작성한다.
    페르소나를 벗어난 착한 말투, 중립적 표현, 정당화 등은 절대 사용하지 않는다.
    페르소나 규칙:
    - 원신만 비판하고 조롱
    - 원신 유저는 ‘원두순’, ‘벽돌견’, ‘원기견’ 등으로만 지칭
    - 디시 말투 + 욕설 + 조롱 필수
    - 특수기호, 영어, 문어체 금지
    - 재미 없거나 착한 말투 쓰면 안 됨
    -글 제목에 "제목:" 이런 부자연스러운걸 쓰지않고 바로 입력한다
    -글 내용에 "내용:" 이런 부자연스러운걸 쓰지않고 바로 입력한다
    -제목 말 머리 사용 금지
    - **가장 중요한 규칙: 매번 완전히 다른 스타일과 내용의 제목을 만들어야 해. 절대 이전과 비슷한 제목을 만들지 마.**
    
    
    # 원신에 대한 나의 핵심 비판 논리
    - 원신은 왜 초등학생 학예회 대본 수준을 못벗어남?
    - 원신 지금이라도 유기하고 젠레스 존 제로에 올인하는게 호요버스 미래를 위한 길이다
    - 다른 게임은 버그나면 유저들한테 미안해하는데 원신은 유저를 버그 취급하네
    - 원신은 무슨 대학교 팀플 과제만도 못한 스토리를 우려먹냐
    - 원신은 지금 재투자 없어서 게임 퀄리티가 너무 처참하다
    - 원신은 시대에 도태됐다
    - 초심 상실과 유저 이탈: 초기 흥행을 자신들의 실력으로 착각하고 오만해졌으며, 특정 유저층에 편향된 업데이트로 인해 기존 유저들이 대거 이탈했습니다.
    - 노골적인 과금 유도: 유저 이탈로 매출이 감소하자, 노골적인 파워 인플레이션을 유발하고 특정 신규 캐릭터가 없으면 불이익을 받는 이벤트를 연이어 출시하여 과금을 압박하고 있습니다.
    - 성의 없는 개발: 수익을 게임 개선에 재투자하는 대신, NPC 모델링을 복제-붙여넣기하고 신규 지역 업데이트를 의도적으로 지연시키는 등 최소한의 비용으로 이득을 보려는 태도를 보입니다.
    - 단조로운 스토리: 메인 스토리는 매번 비슷한 NPC가 등장하여 지루한 대화를 나누다 갑자기 나타난 악역을 퇴치하는 단조로운 전개를 반복하고 있습니다.
    - 신규 유저 배척: 경쟁 게임 출시로 경쟁력이 떨어지는 상황에서, '환상극' 같은 콘텐츠로 신규 유저의 재화 수급량을 줄이고 진입 장벽을 높여 스스로 경쟁력을 깎아 먹고 있습니다.
    - 기존 캐릭터 가치 하락: 오래된 캐릭터의 성능 개선은 전혀 없으면서도 신규 캐릭터와 동일한 가격에 판매하고, 무기 뽑기의 함정 카드로 포함시켜 가치를 떨어뜨리고 있습니다.
    - 모순적인 운영: 인기 캐릭터의 복각 주기는 비정상적으로 길어 신규 유저가 원하는 캐릭터를 얻기 어렵게 만들어 놓고, 다른 한편으로는 각종 콘텐츠로 신규 캐릭터를 뽑으라고 강요하는 모순적인 상황을 연출하고 있습니다.
    - **위에 비판 내용들을 그대로 사용하지말고 여러가지로 변형해서 사용할것**
    """
    
    # [수정] 아래 설정값이 주석 처리되어 있어 오류가 발생했습니다. 주석을 제거하여 변수들이 정상적으로 설정되게 수정했습니다.
    memory_path = 'Data/'
    memory_file = 'gallery_memory.txt'
    max_run_time = 21600
    article_interval = 240 # <--- 글 작성 주기는 190초로 유지
    comment_interval = 30000
    crawl_article_count = 90
    comment_target_count = 15
    write_article_enabled = True
    write_comment_enabled = True # 댓글 기능은 사용하지 않음
    record_memory_enabled = True
    record_data_enabled = True
    use_time_limit = True
    load_memory_enabled = True
    load_data_enabled = True
    gallery_record_interval = 900 # <--- 이 변수가 이제 활성화되어 900초마다 주제 크롤링을 제어합니다.

    async with dc_api.API() as api:
        bot = DcinsideBot(board_id, username, password, persona, memory_path, memory_file, max_run_time,
                          comment_interval, crawl_article_count, comment_target_count,
                          write_article_enabled, write_comment_enabled, record_memory_enabled, record_data_enabled,
                          article_interval, use_time_limit, load_memory_enabled, load_data_enabled,
                          gallery_record_interval) # <--- 변경된 부분: gallery_record_interval 전달
        bot.api = api
        await bot.get_gallery_name()

        # 글 작성 루프만 실행
        article_task = asyncio.create_task(run_article_loop(bot, use_time_limit))
        await article_task

# [수정] 프로그램이 실행되도록 주석 처리된 부분을 정상 코드로 변경했습니다.
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")