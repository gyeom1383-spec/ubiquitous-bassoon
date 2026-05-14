import streamlit as st
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# ── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(
    page_title="정서를 표현하는 글 쓰기",
    page_icon="✍️",
    layout="centered",
)

# ── 스타일 ──────────────────────────────────────────────────
st.markdown("""
<style>
  .step-header {
    background: #1B5E20; color: white;
    padding: 10px 18px; border-radius: 8px;
    font-size: 1.05rem; font-weight: 700;
    margin-bottom: 12px;
  }
  .step-inactive {
    background: #E8F5E9; color: #2E7D32;
    padding: 10px 18px; border-radius: 8px;
    font-size: 1.0rem; font-weight: 600;
    margin-bottom: 6px;
  }
  .tip-box {
    background: #FFFDE7; border-left: 4px solid #F9A825;
    padding: 10px 14px; border-radius: 4px;
    font-size: 0.92rem; margin-bottom: 10px;
  }
  .ai-box {
    background: #E8F5E9; border-left: 4px solid #2E7D32;
    padding: 12px 16px; border-radius: 4px;
    font-size: 0.95rem; margin-top: 12px;
  }
</style>
""", unsafe_allow_html=True)

# ── Gemini API 키 자동 전환 ──────────────────────────────────
def get_api_keys():
    """secrets에서 API 키 목록을 가져옴 (세 가지 형식 모두 호환)"""
    # 형식 1: GEMINI_API_KEYS = ["key1", "key2", ...] (리스트)
    if "GEMINI_API_KEYS" in st.secrets:
        keys = list(st.secrets["GEMINI_API_KEYS"])
        if keys:
            return keys
    # 형식 2: GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... (개별)
    keys = []
    i = 1
    while True:
        key_name = f"GEMINI_API_KEY_{i}"
        if key_name in st.secrets:
            keys.append(st.secrets[key_name])
            i += 1
        else:
            break
    if keys:
        return keys
    # 형식 3: GEMINI_API_KEY = "key" (단일)
    if "GEMINI_API_KEY" in st.secrets:
        return [st.secrets["GEMINI_API_KEY"]]
    return []

def ai_call(prompt: str) -> str:
    """API 키를 순서대로 시도, 할당량 초과 시 다음 키로 자동 전환 (OpenAI 호환 엔드포인트)"""
    keys = get_api_keys()
    last_error = None
    for idx, key in enumerate(keys):
        try:
            client = OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            resp = client.chat.completions.create(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=3000,
                temperature=0.3,
            )
            return resp.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                last_error = e
                continue
            raise e
    raise Exception(f"모든 API 키의 할당량이 초과되었습니다. 잠시 후 다시 시도해 주세요.\n(마지막 오류: {last_error})")

# ── Google Sheets 연결 ───────────────────────────────────────
@st.cache_resource
def get_sheet():
    """Google Sheets 연결 (캐시로 재연결 최소화)"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/1O-mP0-STtqsyUdCt6iHmCM8qRs88WeQMo3BgV2vrBkc/edit"
    ).sheet1
    return sheet

def log_to_sheet(student_id, name, step_name, content, feedback=""):
    """스프레드시트에 한 행 기록 (최대 3회 재시도)"""
    import time
    for attempt in range(3):
        try:
            sheet = get_sheet()
            existing = sheet.get_all_values()
            if not existing:
                sheet.append_row(["학번", "이름", "글쓰기 단계", "제출 내용", "피드백 내용", "제출 시각"])
            sheet.append_row([
                student_id,
                name,
                step_name,
                content,
                feedback,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            return  # 성공 시 종료
        except Exception as e:
            if attempt < 2:
                time.sleep(2)  # 2초 후 재시도
            else:
                st.warning(f"기록 저장 중 오류가 발생했어요: {e}")

# ── 세션 초기화 ─────────────────────────────────────────────
defaults = {
    "step": 0,           # 0 = 학생 정보 입력
    "student_id": "",
    "student_name": "",
    "plan": {},
    "memo": "",
    "structure": "",
    "structure_fb": "",
    "draft": "",
    "checklist": {},
    "revise_fb": "",
    "final": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헬퍼 ────────────────────────────────────────────────────
def go(step):
    st.session_state.step = step
    st.rerun()

def step_label(n, title, active):
    tag = "step-header" if active else "step-inactive"
    label = f"STEP {n}  |  {title}" if n > 0 else title
    st.markdown(f'<div class="{tag}">{label}</div>', unsafe_allow_html=True)

def student_info_bar():
    sid = st.session_state.student_id
    name = st.session_state.student_name
    if sid or name:
        st.caption(f"👤 {sid}  {name}")

# ══════════════════════════════════════════════════════════════
# STEP 0 · 학생 정보 입력
# ══════════════════════════════════════════════════════════════
if st.session_state.step == 0:
    st.markdown('<div class="step-header">✍️ 정서를 표현하는 글 쓰기</div>',
                unsafe_allow_html=True)
    st.caption("시작하기 전에 학번과 이름을 입력해 주세요.")

    student_id = st.text_input("학번", placeholder="예) 10101",
                               value=st.session_state.student_id)
    student_name = st.text_input("이름", placeholder="예) 홍길동",
                                 value=st.session_state.student_name)

    if st.button("시작하기 →", type="primary"):
        if not student_id.strip() or not student_name.strip():
            st.warning("학번과 이름을 모두 입력해 주세요.")
        else:
            st.session_state.student_id = student_id.strip()
            st.session_state.student_name = student_name.strip()
            go(1)

# ══════════════════════════════════════════════════════════════
# STEP 1 · 계획하기
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 1:
    student_info_bar()
    step_label(1, "계획하기", True)
    st.caption("글을 쓰기 전, 무엇을 어떻게 쓸지 계획해 봅시다.")

    st.markdown('<div class="tip-box">💡 사소한 경험이어도 괜찮아요. '
                '나에게 <b>의미 있었던</b> 순간이면 충분합니다.</div>',
                unsafe_allow_html=True)

    glam = st.text_area("① 글감 (어떤 경험을 쓸 건가요?)",
                        value=st.session_state.plan.get("glam", ""),
                        placeholder="예) 엘리베이터 공사로 계단을 오르내리다 옆집 할머니를 도운 일",
                        height=80)
    emotion = st.text_input("② 중심 정서 (그때 가장 크게 느낀 감정)",
                            value=st.session_state.plan.get("emotion", ""),
                            placeholder="예) 처음엔 짜증스러웠지만, 도와드린 뒤 뿌듯했다")
    method = st.multiselect("③ 활용할 표현 방법 (하나 이상 선택)",
                            ["운율", "비유", "상징"],
                            default=st.session_state.plan.get("method", []))

    if st.button("다음 단계로 →", type="primary"):
        if not glam.strip() or not emotion.strip() or not method:
            st.warning("세 항목을 모두 입력해 주세요.")
        else:
            st.session_state.plan = {"glam": glam, "emotion": emotion, "method": method}
            content = f"글감: {glam}\n중심 정서: {emotion}\n표현 방법: {', '.join(method)}"
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "① 계획하기", content)
            go(2)

# ══════════════════════════════════════════════════════════════
# STEP 2 · 내용 생성하기
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 2:
    student_info_bar()
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", True)
    st.caption("경험을 자유롭게 떠올려 메모해 봅시다. 형식은 신경 쓰지 않아도 돼요.")

    p = st.session_state.plan
    st.info(f"📌 글감: {p['glam']}  |  중심 정서: {p['emotion']}  |  표현 방법: {', '.join(p['method'])}")

    st.markdown('<div class="tip-box">💡 생각나는 장면, 대화, 감정, 색깔, 소리 등 '
                '떠오르는 것을 모두 적어보세요. 양이 많을수록 좋아요!</div>',
                unsafe_allow_html=True)

    memo = st.text_area("자유 메모",
                        value=st.session_state.memo,
                        placeholder="예)\n- 176개 계단, 숨이 턱까지 차오름\n- 체육복 소매가 자전거에 걸려 찢어짐\n- 할머니 흰 머리카락, 힘겨운 한숨 소리\n- 돕고 싶은데 학원 늦을까봐 망설임\n- 짐 들어드리는 순간 마음이 가벼워짐",
                        height=220)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(1)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if len(memo.strip()) < 20:
                st.warning("조금 더 자세히 메모해 주세요.")
            else:
                st.session_state.memo = memo
                log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                             "② 내용 생성하기", memo)
                go(3)

# ══════════════════════════════════════════════════════════════
# STEP 3 · 내용 조직하기  ★ AI 개입
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 3:
    student_info_bar()
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기 ✦ AI 피드백", True)
    st.caption("메모한 내용을 글의 순서대로 정리해 봅시다.")

    p = st.session_state.plan
    st.info(f"📌 중심 정서: {p['emotion']}")

    st.markdown('<div class="tip-box">💡 각 문단에 <b>일어난 일</b>과 <b>그때 느낀 감정</b>을 함께 써 보세요. '
                '처음(시작) → 중간1 → 중간2 → 중간3 → 끝(결말·깨달음) 순서로 구성해요.</div>',
                unsafe_allow_html=True)

    para_labels = [
        ("1문단", "처음 (시작 장면·상황)"),
        ("2문단", "중간1 (사건 전개)"),
        ("3문단", "중간2 (변화·갈등)"),
        ("4문단", "중간3 (전환·결심)"),
        ("5문단", "끝 (결말·깨달음)"),
    ]

    # 세션에서 각 문단 불러오기
    if "structure_paras" not in st.session_state:
        st.session_state.structure_paras = [""] * 5

    paras = []
    for i, (num, hint) in enumerate(para_labels):
        val = st.text_area(
            f"**{num}** — {hint}",
            value=st.session_state.structure_paras[i],
            placeholder=f"예) {['엘리베이터 공사로 계단을 오르내려야 했다. 힘들고 짜증스러웠다.', '자전거 소매가 걸려 체육복이 찢어졌다. 불길한 기분이 들었다.', '학원 가는 길에 무거운 짐을 든 할머니와 마주쳤다. 안쓰러웠지만 모른 척하고 싶었다.', '고민 끝에 할머니의 짐을 들어드리기로 결심했다.', '계단을 함께 오르며 마음이 가벼워졌다. 작은 용기가 뿌듯함으로 돌아왔다.'][i]}",
            height=90,
            key=f"para_{i}"
        )
        paras.append(val)
    st.session_state.structure_paras = paras

    structure = "\n".join(
        f"{label[0]}: {p}" for label, p in zip(para_labels, paras) if p.strip()
    )
    all_filled = all(p.strip() for p in paras)

    if st.button("🤖 AI 피드백 받기", type="primary", disabled=not all_filled):
        with st.spinner("AI가 구성을 분석하고 있어요..."):
            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 지도하는 교사입니다.
학생이 '정서를 표현하는 글 쓰기' 수행평가를 위해 글의 구성을 짰습니다.
친절하지만 사실에 기반한 솔직하고 단호한 피드백을 제공하세요.
칭찬보다는 실질적인 개선 방향을 중심으로 작성하세요.

[학생 정보]
- 글감: {p['glam']}
- 중심 정서: {p['emotion']}
- 활용할 표현 방법: {', '.join(p['method'])}
- 자유 메모: {st.session_state.memo}

[학생이 짠 글의 구성·순서]
{structure}

[피드백 지침]
반드시 아래 두 파트로만 구성하세요.

**[구성 평가]**
현재 구성의 부족한 점을 사실에 근거하여 솔직하게 지적하세요.
- 중심 정서({p['emotion']})가 각 문단에서 잘 드러나는지 구체적으로 평가
- 문단 흐름이 자연스러운지, 어색한 부분이 있다면 어느 문단인지 명확히 지적
- 막연한 칭찬은 하지 말고, 실제로 잘된 부분이 있을 때만 한 문장 언급
- 없으면 부족한 점만 솔직하게 서술

**[스스로 점검할 질문]**
학생이 구성을 스스로 고칠 수 있도록 구체적인 방향을 담은 질문 2개를 제시하세요.
- 단순한 "잘 되었나요?" 형태가 아니라, 학생이 무엇을 어떻게 고쳐야 할지 생각하게 만드는 질문
- 예: "2문단에서 감정 변화가 나타나지 않는데, 이 장면에서 네가 느낀 감정을 한 문장 추가한다면 어떤 감정을 넣겠어?"
- 답을 직접 알려주지 말고, 스스로 생각하게 열어두세요.
총 200자 내외로 작성하세요."""

            fb = ai_call(prompt)
            st.session_state.structure_fb = fb
            # 구성 + 피드백 함께 기록
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "③ 내용 조직하기", structure, fb)

    if st.session_state.structure_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.structure_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(2)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if not structure.strip():
                st.warning("구성을 먼저 작성해 주세요.")
            else:
                st.session_state.structure = structure
                go(4)

# ══════════════════════════════════════════════════════════════
# STEP 4 · 초고 쓰기
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 4:
    student_info_bar()
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기", False)
    step_label(4, "초고 쓰기", True)
    st.caption("조직한 내용을 바탕으로 글을 써 봅시다.")

    p = st.session_state.plan
    st.info(f"📌 중심 정서: {p['emotion']}  |  표현 방법: {', '.join(p['method'])}")

    st.markdown('<div class="tip-box">💡 맞춤법이나 문장이 완벽하지 않아도 괜찮아요. '
                '지금은 내 생각과 감정을 글로 꺼내는 것이 가장 중요해요. '
                '<b>200자 이상 400자 이내</b>로 써보세요.</div>',
                unsafe_allow_html=True)

    title = st.text_input("제목", placeholder="글의 제목을 입력하세요",
                          value=st.session_state.plan.get("title", ""))
    draft = st.text_area("초고",
                         value=st.session_state.draft,
                         placeholder="여기에 글을 써 주세요...",
                         height=320)

    char_count = len(draft.replace(" ", "").replace("\n", ""))
    st.caption(f"현재 글자 수 (공백·줄바꿈 제외): {char_count}자")
    if char_count < 200:
        st.warning(f"200자 이상 써주세요. (현재 {char_count}자)")
    elif char_count > 400:
        st.warning(f"400자 이내로 줄여주세요. (현재 {char_count}자)")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(3)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if char_count < 200:
                st.warning("200자 이상 써야 다음 단계로 넘어갈 수 있어요.")
            elif not title.strip():
                st.warning("제목을 입력해 주세요.")
            else:
                st.session_state.draft = draft
                st.session_state.plan["title"] = title
                content = f"제목: {title}\n\n{draft}"
                log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                             "④ 초고 쓰기", content)
                go(5)

# ══════════════════════════════════════════════════════════════
# STEP 5 · 고쳐쓰기  ★ AI 개입
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 5:
    student_info_bar()
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기", False)
    step_label(4, "초고 쓰기", False)
    step_label(5, "고쳐쓰기 ✦ AI 피드백", True)
    st.caption("내 글을 스스로 점검하고, AI의 도움을 받아 다듬어 봅시다.")

    with st.expander("📄 내 초고 보기", expanded=False):
        st.markdown(f"**{st.session_state.plan.get('title', '')}**")
        st.write(st.session_state.draft)

    st.divider()
    st.markdown("#### 📋 자기 점검 체크리스트")
    st.caption("먼저 스스로 점검해 본 뒤, AI 피드백을 받으세요.")

    checks = {
        "c1": "특정 경험이나 장면이 구체적으로 드러나 있다.",
        "c2": "'슬프다', '좋다' 같은 막연한 감정어 대신 상황과 연결된 감정을 표현했다.",
        "c3": "운율·비유·상징 중 하나 이상을 의도적으로 활용했다.",
        "c4": "중심 정서가 글의 처음부터 끝까지 일관되게 유지된다.",
        "c5": "글의 처음과 끝이 자연스럽게 연결된다.",
    }
    check_results = {}
    for key, label in checks.items():
        check_results[key] = st.checkbox(label, value=st.session_state.checklist.get(key, False))
    st.session_state.checklist = check_results

    st.divider()
    st.markdown("#### 🤖 AI 표현·문장 점검")

    if st.button("AI 피드백 받기", type="primary"):
        with st.spinner("AI가 문장을 꼼꼼히 살펴보고 있어요..."):
            unchecked = [label for key, label in checks.items() if not check_results[key]]
            checklist_summary = ("모든 항목을 체크했습니다." if not unchecked
                                 else f"아직 점검이 필요한 항목: {', '.join(unchecked)}")

            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 지도하는 교사입니다.
표현과 문장 수준의 피드백만 제공하세요. 내용·구성은 다루지 마세요.
친절하지만 사실에 기반한 솔직하고 단호한 피드백을 제공하세요.
부족한 부분은 명확하게 지적하고, 학생 스스로 어떻게 고쳐야 할지 생각하게 만드세요.

[학생 글]
제목: {st.session_state.plan.get('title', '')}
{st.session_state.draft}

[자기 점검 결과]
{checklist_summary}

[피드백 지침]
반드시 아래 두 파트로만 구성하세요.

**[표현 평가]**
- 맞춤법 오류가 있으면 반드시 지적 (예: '됬다' → '됐다')
- 어색하거나 반복되는 문장은 해당 문장을 직접 인용하여 왜 어색한지 설명
- 자기 점검에서 체크하지 않은 항목이 있다면 그 부분도 반드시 언급
- 부족한 점이 없을 때만 "표현과 문장이 전반적으로 자연스럽습니다."라고 쓰세요.
- 최대 3가지까지

**[고쳐쓰기 미션]**
학생이 스스로 고칠 수 있도록 구체적인 행동 방향을 제시하세요.
- "~을 어떻게 고치면 좋을까?" 형태로 학생이 직접 생각하게 유도
- 수정 예시를 직접 써주지 말고, 어떤 방향으로 고쳐야 하는지만 안내
- 부족한 점이 없으면 "이 글에서 특히 잘된 표현은 어디라고 생각해? 그 이유도 함께 생각해봐."라고 쓰세요.
- 총 200자 내외

절대로 글의 내용을 대신 써주거나 수정된 문장을 직접 제공하지 마세요."""

            fb = ai_call(prompt)
            st.session_state.revise_fb = fb

            # 초고 + 체크리스트 결과 + 피드백 기록
            checked_items = [label for key, label in checks.items() if check_results[key]]
            content = (f"[자기 점검 완료 항목]\n" +
                       "\n".join(f"✓ {c}" for c in checked_items) +
                       f"\n\n[초고]\n제목: {st.session_state.plan.get('title', '')}\n{st.session_state.draft}")
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "⑤ 고쳐쓰기", content, fb)

    if st.session_state.revise_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.revise_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    st.divider()
    st.markdown("#### ✍️ 최종 수정본")
    final = st.text_area("AI 피드백을 반영해 글을 고쳐 쓰세요.",
                         value=st.session_state.draft,
                         height=300)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(4)
    with col2:
        if st.button("✅ 최종 제출", type="primary"):
            st.session_state.final = final
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "✅ 최종 제출",
                         f"제목: {st.session_state.plan.get('title', '')}\n\n{final}")
            go(6)

# ══════════════════════════════════════════════════════════════
# STEP 6 · 완료
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 6:
    st.balloons()
    st.success("✅ 글쓰기를 모두 마쳤어요! 수고했습니다.")

    p = st.session_state.plan
    st.markdown(f"### {p.get('title', '나의 글')}")
    st.write(st.session_state.get("final", st.session_state.draft))

    st.divider()
    st.markdown("**📊 나의 글쓰기 과정 요약**")
    st.markdown(f"- 글감: {p.get('glam', '')}")
    st.markdown(f"- 중심 정서: {p.get('emotion', '')}")
    st.markdown(f"- 활용한 표현 방법: {', '.join(p.get('method', []))}")
    checked = sum(1 for v in st.session_state.checklist.values() if v)
    st.markdown(f"- 자기 점검: {checked}/5 항목 완료")
